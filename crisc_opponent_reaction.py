import duckdb
import pandas as pd
import sys

if len(sys.argv) < 3:
    print("Usage: python crisc_opponent_reaction.py <FILE_ID> <MONTH> [data_dir]")
    sys.exit(1)

file_id = sys.argv[1]
month = sys.argv[2]
data_dir = sys.argv[3] if len(sys.argv) >= 4 else "./data"

print("Joining Datasets to Calculate Average Reaction Time (R_O)...")

con = duckdb.connect()

# 1. Load your True CRISCs into DuckDB's memory as a temporary table
con.execute(f"CREATE TABLE criscs AS SELECT * FROM read_csv_auto('./true_criscs/true_criscs_{file_id}.csv')")

# 2. Perform a massive JOIN to extract the clocks for ONLY our filtered games
query = f"""
SELECT 
    r.lichess_id, 
    r.ply, 
    r.crisc_player, 
    p.clocks_white, 
    p.clocks_black
FROM criscs r
JOIN '{data_dir}/aix_lichess_{month}_low.parquet' p ON r.lichess_id = p.lichess_id
"""
results = con.execute(query).df()

total_reaction_time = 0
valid_games = 0

print("Calculating cognitive delay...")

# 3. Calculate the time burned by the victim
for index, row in results.iterrows():
    ply = int(row['ply'])
    player = row['crisc_player']
    clocks_white = row['clocks_white']
    clocks_black = row['clocks_black']
    
    try:
        # Chess clocks are recorded per full move (ply // 2)
        move_index = ply // 2
        
        if player == 'White':
            # White played the CRISC. Black is the victim reacting.
            # We measure Black's clock BEFORE they react, and AFTER they react.
            time_before = int(clocks_black[move_index - 1])
            time_after = int(clocks_black[move_index])
        else:
            # Black played the CRISC. White is the victim reacting.
            time_before = int(clocks_white[move_index - 1])
            time_after = int(clocks_white[move_index])
            
        reaction_time = time_before - time_after
        
        # Filter out pre-moves (exactly 0) and weird server lag artifacts (negative)
        if reaction_time > 0:
            total_reaction_time += reaction_time
            valid_games += 1
            
    except Exception as e:
        continue

if valid_games > 0:
    avg_ro = total_reaction_time / valid_games
    print(f"\nSuccessfully analyzed {valid_games} games.")
    print(f"--- AVERAGE REACTION TIME (R_O) ---")
    print(f"{avg_ro:.2f} seconds")
else:
    print("Could not calculate R_O.")
