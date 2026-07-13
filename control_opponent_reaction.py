import os
import subprocess
import re
import csv
import duckdb
import pandas as pd

months = ["2026-02", "2026-03", "2026-04"]
SAMPLE_SIZE = 21500

# ============================================================
# SQL Template: Sound checks (Delta_E >= -50) with T_O <= 5
# Randomly sample exactly 21,500 per month to balance N
# ============================================================
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
        FROM './data/aix_lichess_{MONTH}_low.parquet'
        WHERE 
            time_increment = 0 
            AND time_initial IN (60, 180)
            AND length(evals) >= 2
    ),
    sound_checks AS (
        SELECT 
            lichess_id,
            ply,
            result,
            CASE WHEN ply % 2 = 1 THEN 'White' ELSE 'Black' END AS crisc_player
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
            ) >= -50
    )
    SELECT * FROM sound_checks ORDER BY random() LIMIT {SAMPLE_SIZE}
) TO './control_checks/control_checks_{MONTH}.csv' (HEADER, DELIMITER ',');
"""

# ============================================================
# Main Loop: Extract + Calculate R_O for each month
# ============================================================
total_ro_time = 0
total_ro_games = 0
month_results = []

for month in months:
    print(f"\n============================")
    print(f"Processing Control Group: {month}")
    print(f"============================")

    # --- DuckDB extraction with random sampling ---
    sql_query = sql_template.format(MONTH=month, SAMPLE_SIZE=SAMPLE_SIZE)
    sql_file = f"./control_filter/control_filter_{month}.sql"
    with open(sql_file, "w") as f:
        f.write(sql_query)

    print(f"Running DuckDB control extraction for {month}...")
    subprocess.run(["./duckdb", "-unsigned", "-c", f".read {sql_file}"], check=True)

    # --- Calculate reaction time via JOIN back to parquet ---
    print(f"Calculating control reaction time for {month}...")
    con = duckdb.connect()
    con.execute(f"CREATE TABLE controls AS SELECT * FROM read_csv_auto('./control_checks/control_checks_{month}.csv')")

    query = f"""
    SELECT 
        c.lichess_id, 
        c.ply, 
        c.crisc_player, 
        p.clocks_white, 
        p.clocks_black
    FROM controls c
    JOIN './data/aix_lichess_{month}_low.parquet' p ON c.lichess_id = p.lichess_id
    """
    results = con.execute(query).df()
    con.close()

    month_ro_time = 0
    month_valid = 0

    for _, row in results.iterrows():
        ply = int(row['ply'])
        player = row['crisc_player']
        clocks_white = row['clocks_white']
        clocks_black = row['clocks_black']

        try:
            move_index = ply // 2

            if player == 'White':
                time_before = int(clocks_black[move_index - 1])
                time_after = int(clocks_black[move_index])
            else:
                time_before = int(clocks_white[move_index - 1])
                time_after = int(clocks_white[move_index])

            reaction_time = time_before - time_after

            # Filter out pre-moves (exactly 0) and server lag artifacts (negative)
            if reaction_time > 0:
                month_ro_time += reaction_time
                month_valid += 1

        except Exception:
            continue

    month_avg_ro = month_ro_time / month_valid if month_valid > 0 else 0
    month_results.append({
        'month': month,
        'avg_ro': month_avg_ro,
        'valid_games': month_valid,
        'total_sampled': len(results)
    })

    total_ro_time += month_ro_time
    total_ro_games += month_valid

    print(f"Month {month}: Control R_O = {month_avg_ro:.2f}s ({month_valid} valid games)")

# ============================================================
# Final Aggregation
# ============================================================
overall_ro = total_ro_time / total_ro_games if total_ro_games > 0 else 0

with open("./results/control_group_results_T5.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Month", "Control_Reaction_Time", "Valid_Games", "Total_Sampled"])
    for r in month_results:
        writer.writerow([r['month'], f"{r['avg_ro']:.2f}", r['valid_games'], r['total_sampled']])
    writer.writerow(["ALL_MONTHS_COMBINED", f"{overall_ro:.2f}", total_ro_games,
                      sum(r['total_sampled'] for r in month_results)])

print(f"\n============================")
print(f"CONTROL GROUP ANALYSIS COMPLETE!")
print(f"Total Valid Control Games: {total_ro_games}")
print(f"--- COMBINED CONTROL REACTION TIME (R_O) ---")
print(f"{overall_ro:.2f} seconds")
print(f"Saved to './results/control_group_results_T5.csv'")
