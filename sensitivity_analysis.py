import os
import subprocess
import sys
import re
import csv

# Create required directory structure
for folder in ["./candidate_criscs", "./true_criscs", "./results", "./crisc_sql_filter", "./control_checks", "./control_filter"]:
    os.makedirs(folder, exist_ok=True)

# Configuration: Target dataset and threshold permutations
DATA_MONTH = "2026-04"
DATA_DIR = "./data"  # Change to "./data_sample" for Path A (Quick Evaluation)

permutations = [
    (5, 400),
    (10, 400),
    (15, 400),
    (15, 200),
    (15, 300)
]

sql_template = """INSTALL aixchess FROM community;
LOAD aixchess;

COPY (
    WITH exploded_games AS (
        SELECT 
            lichess_id,
            result,
            UNNEST(range(2, length(evals) + 1)) AS ply,
            evals,
            clocks_white,
            clocks_black,
            move_details(movedata) AS moves
        FROM '{DATA_DIR}/aix_lichess_{MONTH}_low.parquet'
        WHERE 
            time_increment = 0 
            AND time_initial IN (60, 180)
            AND length(evals) >= 2
    )
    SELECT 
        lichess_id,
        ply,
        result,
        CASE WHEN ply % 2 = 1 THEN 'White' ELSE 'Black' END AS crisc_player,
        [m."from" || m."to" || m.promotion FOR m IN moves] AS move_list
    FROM exploded_games
    WHERE 
        moves[ply].is_check = TRUE
        AND (
            CASE 
                WHEN ply % 2 = 1 THEN clocks_black[CAST(floor(ply / 2.0) AS INTEGER)] 
                ELSE clocks_white[CAST(floor(ply / 2.0) AS INTEGER)]
            END
        ) <= {T_O}
        AND (
            CASE 
                WHEN ply % 2 = 1 THEN eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])
                ELSE (eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])) * -1
            END
        ) <= -{DELTA_E}
) TO './candidate_criscs/candidate_criscs_{PERM_ID}.csv' (HEADER, DELIMITER ',');
"""

with open("./results/sensitivity_analysis_results.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["T_O", "Delta_E", "Win_Rate", "Reaction_Time", "N"])

for to, de in permutations:
    perm_id = f"T{to}_E{de}"
    print(f"\n============================")
    print(f"Running Permutation T_O={to}, Delta_E={de}")
    print(f"============================")
    
    sql_query = sql_template.format(T_O=to, DELTA_E=de, MONTH=DATA_MONTH, PERM_ID=perm_id, DATA_DIR=DATA_DIR)
    sql_file = f"./crisc_sql_filter/crisc_sql_filter_{perm_id}.sql"
    with open(sql_file, "w") as f:
        f.write(sql_query)
        
    print("Running Step 1 (DuckDB SQL broad filter)...")
    subprocess.run(["./duckdb", "-unsigned", "-c", f".read {sql_file}"], check=True)
    
    print("Running Step 2 (crisc_geometric_filter.py)...")
    subprocess.run([sys.executable, "crisc_geometric_filter.py", perm_id], check=True)
    
    print("Running scripts for Win Rate & Reaction Time...")
    wr_out = subprocess.run([sys.executable, "crisc_winrate.py", perm_id], capture_output=True, text=True, check=True).stdout
    ro_out = subprocess.run([sys.executable, "crisc_opponent_reaction.py", perm_id, DATA_MONTH, DATA_DIR], capture_output=True, text=True, check=True).stdout
    
    wr_match = re.search(r"--- GLOBAL CRISC WIN RATE ---\n([\d.]+)%", wr_out)
    win_rate = wr_match.group(1) if wr_match else "N/A"
    
    n_match = re.search(r"Total True CRISCs analyzed: (\d+)", wr_out)
    n_count = n_match.group(1) if n_match else "N/A"
    
    ro_match = re.search(r"--- AVERAGE REACTION TIME \(R_O\) ---\n([\d.]+) seconds", ro_out)
    ro = ro_match.group(1) if ro_match else "N/A"
    
    with open("./results/sensitivity_analysis_results.csv", "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([to, de, win_rate, ro, n_count])
        
    print(f"Results: Win Rate {win_rate}%, R_O {ro}s, N {n_count}")

print("\nOrchestration complete!")
