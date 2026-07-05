import os
import subprocess
import sys
import re
import csv

# Create required directory structure
for folder in ["./candidate_riscks", "./true_riscks", "./results", "./risck_sql_filter", "./control_checks", "./control_filter"]:
    os.makedirs(folder, exist_ok=True)

months = ["2026-02", "2026-03", "2026-04"] # Remove "2026-02" and "2026-03" for Path A (Quick Evaluation)
DATA_DIR = "./data"  # Change to "./data_sample" for Path A (Quick Evaluation)

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
        CASE WHEN ply % 2 = 1 THEN 'White' ELSE 'Black' END AS risck_player,
        [m."from" || m."to" || m.promotion FOR m IN moves] AS move_list
    FROM exploded_games
    WHERE 
        moves[ply].is_check = TRUE
        AND (
            CASE 
                WHEN ply % 2 = 1 THEN clocks_black[CAST(floor(ply / 2.0) AS INTEGER)] 
                ELSE clocks_white[CAST(floor(ply / 2.0) AS INTEGER)]
            END
        ) <= 5
        AND (
            CASE 
                WHEN ply % 2 = 1 THEN eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])
                ELSE (eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])) * -1
            END
        ) <= -400
) TO './candidate_riscks/candidate_riscks_{MONTH}.csv' (HEADER, DELIMITER ',');
"""

total_n = 0
total_wins = 0
total_ro_games = 0
total_ro_time = 0

with open("./results/master_scaling_results_T5_E400.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Month", "Win_Rate", "Reaction_Time", "N"])

for month in months:
    print(f"\n============================")
    print(f"Processing Month {month}")
    print(f"============================")
    
    sql_query = sql_template.format(MONTH=month, DATA_DIR=DATA_DIR)
    with open(f"./risck_sql_filter/risck_sql_filter_{month}.sql", "w") as f:
        f.write(sql_query)
        
    print(f"Running Step 1 (DuckDB SQL broad filter) for {month}...")
    subprocess.run(["./duckdb", "-unsigned", "-c", f".read ./risck_sql_filter/risck_sql_filter_{month}.sql"], check=True)
    
    print(f"Running Step 2 (risck_geometric_filter.py) for {month}...")
    subprocess.run([sys.executable, "risck_geometric_filter.py", month], check=True)
    
    print(f"Running scripts for Win Rate & Reaction Time for {month}...")
    wr_out = subprocess.run([sys.executable, "risck_winrate.py", month], capture_output=True, text=True, check=True).stdout
    ro_out = subprocess.run([sys.executable, "risck_opponent_reaction.py", month, DATA_DIR], capture_output=True, text=True, check=True).stdout
    
    # Parse Win Rate output
    wr_match = re.search(r"--- GLOBAL RISCK WIN RATE ---\n([\d.]+)%", wr_out)
    month_wr = float(wr_match.group(1)) if wr_match else 0.0
    
    wins_match = re.search(r"Total games WON after executing a RISCK: (\d+)", wr_out)
    month_wins = int(wins_match.group(1)) if wins_match else 0
    
    n_match = re.search(r"Total True RISCKs analyzed: (\d+)", wr_out)
    month_n = int(n_match.group(1)) if n_match else 0
    
    # Parse Reaction Time output
    ro_match = re.search(r"--- AVERAGE REACTION TIME \(R_O\) ---\n([\d.]+) seconds", ro_out)
    month_ro = float(ro_match.group(1)) if ro_match else 0.0
    
    ro_games_match = re.search(r"Successfully analyzed (\d+) games", ro_out)
    month_ro_games = int(ro_games_match.group(1)) if ro_games_match else 0
    
    # Write individual month result
    with open("./results/master_scaling_results_T5_E400.csv", "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([month, f"{month_wr:.2f}%", f"{month_ro:.2f}", month_n])
    
    # Aggregate
    total_n += month_n
    total_wins += month_wins
    total_ro_games += month_ro_games
    total_ro_time += (month_ro * month_ro_games)
    
    print(f"Month {month} Results: Win Rate {month_wr:.2f}%, R_O {month_ro:.2f}s, N {month_n}")

# Final Aggregation
overall_win_rate = (total_wins / total_n) * 100 if total_n > 0 else 0
overall_ro = (total_ro_time / total_ro_games) if total_ro_games > 0 else 0

with open("./results/master_scaling_results_T5_E400.csv", "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["ALL_MONTHS_COMBINED", f"{overall_win_rate:.2f}%", f"{overall_ro:.2f}", total_n])

print("\n============================")
print("T5_E400 Scaling Reults COMPLETE!")
print(f"Total Combined N: {total_n}")
print(f"Overall Win Rate: {overall_win_rate:.2f}%")
print(f"Overall Reaction Time: {overall_ro:.2f}s")
print("Saved final aggregation to './results/master_scaling_results_T5_E400.csv'")
