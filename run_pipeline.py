import argparse
import os
import re
import subprocess
import sys

import pandas as pd

# Create required directory structure
for folder in ["./candidate_criscs", "./true_criscs", "./crisc_sql_filter", "./baseline_moves", "./baseline_filter"]:
    os.makedirs(folder, exist_ok=True)

# ============================================================
# CLI Arguments
# ============================================================
parser = argparse.ArgumentParser(
    description="CRISC Chess Research Pipeline",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
  # Single month, single permutation (quick eval)
  python run_pipeline.py --months 2026-04 --perm T5_E400 --data ./data_sample

  # Three months, single permutation (full 3-month analysis)
  python run_pipeline.py --months 2026-02 2026-03 2026-04 --perm T5_E400 --data ./data

  # Sensitivity analysis: multiple permutations
  python run_pipeline.py --months 2026-02 2026-03 2026-04 --perm T5_E400 T10_E400 --data ./data
"""
)
parser.add_argument('--months', nargs='+', required=True,
                    help="One or more month IDs (e.g. 2026-02 2026-03 2026-04)")
parser.add_argument('--perm',   nargs='+', required=True,
                    help="One or more permutation IDs (e.g. T5_E400 T10_E400)")
parser.add_argument('--data',   default='./data',
                    help="Path to the data directory (default: ./data)")
args = parser.parse_args()

months   = args.months
perms    = args.perm
data_dir = args.data

# ============================================================
# SQL Template
# ============================================================
sql_template = """INSTALL aixchess FROM community;
LOAD aixchess;

COPY (
    WITH exploded_games AS (
        SELECT
            lichess_id,
            result,
            white_rating,
            black_rating,
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
    ),
    candidate_criscs AS (
        SELECT
            lichess_id,
            ply,
            result,
            CASE WHEN ply % 2 = 1 THEN 'White' ELSE 'Black' END AS player,
            [m."from" || m."to" || m.promotion FOR m IN moves] AS move_list,
            moves,
            white_rating,
            black_rating,
            CASE
                WHEN ply % 2 = 1 THEN clocks_white[CAST(floor(ply / 2.0) AS INTEGER)]
                ELSE clocks_black[CAST(floor(ply / 2.0) AS INTEGER)]
            END AS player_time,
            CASE
                WHEN ply % 2 = 1 THEN clocks_black[CAST(floor(ply / 2.0) AS INTEGER)]
                ELSE clocks_white[CAST(floor(ply / 2.0) AS INTEGER)]
            END AS opponent_time,
            CASE
                WHEN ply % 2 = 1 THEN eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])
                ELSE (eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])) * -1
            END AS eval_drop,
            eval_to_centipawns(evals[ply - 1]) AS pre_move_eval,
            CASE WHEN ply % 2 = 1 THEN white_rating ELSE black_rating END AS player_elo
        FROM exploded_games
    )
    SELECT
        lichess_id,
        ply,
        result,
        player,
        player_elo,
        move_list,
        CASE
            WHEN player_time <= 5  THEN '<={T_O}s vs <=5s'
            WHEN player_time <= 10 THEN '<={T_O}s vs 5-10s'
            WHEN player_time <= 15 THEN '<={T_O}s vs 10-15s'
            WHEN player_time <= 20 THEN '<={T_O}s vs 15-20s'
        END AS time_scramble_bracket
    FROM candidate_criscs
    WHERE
        moves[ply].is_check = TRUE
        AND opponent_time <= {T_O}
        AND player_time <= 20
        AND eval_drop <= -{DELTA_E}
        AND pre_move_eval BETWEEN -150 AND 150
        AND abs(white_rating - black_rating) <= 200
    QUALIFY ROW_NUMBER() OVER (PARTITION BY lichess_id ORDER BY ply ASC) = 1
) TO './candidate_criscs/candidate_criscs_{CRISC_PATH_ID}.csv' (HEADER, DELIMITER ',');
"""

# ============================================================
# Helper: parse permutation string into SQL thresholds
# ============================================================
def parse_perm(perm):
    """Parse 'T5_E400' -> (t_o=5, delta_e=400)"""
    t_o     = int(re.search(r'T(\d+)', perm).group(1))
    delta_e = int(re.search(r'E(\d+)', perm).group(1))
    return t_o, delta_e

# ============================================================
# Helper: run subprocess, inherit stdout/stderr
# ============================================================
def run(cmd):
    subprocess.run(cmd, check=True)

# ============================================================
# Main loop: for each permutation × each month
# ============================================================
for perm in perms:
    t_o, delta_e = parse_perm(perm)
    print(f"\n{'='*60}")
    print(f"PERMUTATION: {perm}  (T_O <= {t_o}s, ΔE <= -{delta_e})")
    print(f"{'='*60}")

    # Step 1: Per-month extraction
    candidate_dfs = []
    for month in months:
        crisc_path_id = f"{month}_{perm}"
        print(f"\n--- Step 1: Extracting [{month}] ---")

        sql = sql_template.format(
            DATA_DIR=data_dir,
            MONTH=month,
            T_O=t_o,
            DELTA_E=delta_e,
            CRISC_PATH_ID=crisc_path_id
        )
        sql_file = f"./crisc_sql_filter/crisc_sql_filter_{crisc_path_id}.sql"
        with open(sql_file, "w") as f:
            f.write(sql)

        run(["./duckdb", "-unsigned", "-c", f".read {sql_file}"])

        month_df = pd.read_csv(f"./candidate_criscs/candidate_criscs_{crisc_path_id}.csv")
        candidate_dfs.append(month_df)
        print(f"Extracted {len(month_df)} candidates from {month}")

    # Step 2: Concatenate if multi-month, then geometric filter
    if len(months) == 1:
        master_crisc_path_id = f"{months[0]}_{perm}"
    else:
        master_crisc_path_id = f"{months[0]}~{months[-1]}_{perm}"
        master_df = pd.concat(candidate_dfs, ignore_index=True)
        master_df.to_csv(f"./candidate_criscs/candidate_criscs_{master_crisc_path_id}.csv", index=False)
        print(f"\nConcatenated {len(master_df)} total candidates -> candidate_criscs_{master_crisc_path_id}.csv")

    print(f"\n--- Step 2: Geometric Filter [{master_crisc_path_id}] ---")
    run([sys.executable, "crisc_geometric_filter.py", master_crisc_path_id])

    # Step 3: Win rate & Elo stratification
    print(f"\n--- Step 3: Win Rate & Elo Analysis ---")
    run([sys.executable, "winrate.py", master_crisc_path_id] + months)

    # Step 4: Reaction time — once per month
    print(f"\n--- Step 4: Reaction Time (R_O) ---")
    for month in months:
        run([sys.executable, "opponent_reaction.py", master_crisc_path_id, month, data_dir])

print(f"\n{'='*60}")
print("Pipeline complete!")
print(f"{'='*60}")
