import argparse
import duckdb
import math
import os
import numpy as np
import pandas as pd
import sys

parser = argparse.ArgumentParser(description="CRISC & Baseline Opponent Reaction Time Analysis")
parser.add_argument("--months", nargs="+", required=True, help="List of months (e.g. 2026-02 2026-03 2026-04)")
parser.add_argument("--perm", default="T5_E400", help="Permutation ID (default: T5_E400)")
parser.add_argument("--data", default="./data", help="Data directory containing Parquet files")
args = parser.parse_args()

months = args.months
perm = args.perm
data_dir = args.data

month_id = months[0] if len(months) == 1 else f"{months[0]}~{months[-1]}"
crisc_path_id = f"{month_id}_{perm}"

ELO_TIERS = [
    ('< 1000', 0, 999),
    ('1000 - 1500', 1000, 1500),
    ('1500 - 2000', 1500, 2000),
    ('> 2000', 2000, 9999)
]

def compute_ro_records(csv_path, parquet_path):
    """Join a filtered CSV against a raw parquet to compute per-game reaction times."""
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return pd.DataFrame()

    con = duckdb.connect()
    table_name = "dataset"
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{csv_path}')")

    cols = con.execute(f"DESCRIBE {table_name}").df()['column_name'].tolist()
    p_col = 'player' if 'player' in cols else 'crisc_player'
    e_col = 'player_elo' if 'player_elo' in cols else 'attacker_elo'

    results = con.execute(f"""
        SELECT 
            d.lichess_id, 
            d.ply, 
            d.{p_col} AS player,
            d.{e_col} AS player_elo,
            d.time_scramble_bracket,
            p.clocks_white, 
            p.clocks_black
        FROM {table_name} d
        JOIN '{parquet_path}' p ON d.lichess_id = p.lichess_id
    """).df()
    con.close()

    valid_records = []

    for _, row in results.iterrows():
        ply = int(row['ply'])
        player = row['player']
        clocks_white = row['clocks_white']
        clocks_black = row['clocks_black']

        try:
            move_index = ply // 2

            if player == 'White':
                # White played the move at this ply. Black (opponent) reacts next.
                time_before = int(clocks_black[move_index - 1])
                time_after = int(clocks_black[move_index])
            else:
                # Black played the move at this ply. White (opponent) reacts next.
                time_before = int(clocks_white[move_index - 1])
                time_after = int(clocks_white[move_index])

            reaction_time = time_before - time_after

            # Filter pre-moves (R_O=0) and server lag underflow artifacts (R_O<0)
            if reaction_time > 0:
                valid_records.append({
                    'reaction_time': reaction_time,
                    'player_elo': int(row['player_elo']),
                    'time_scramble_bracket': row['time_scramble_bracket']
                })

        except Exception:
            continue

    return pd.DataFrame(valid_records)

def build_ro_matrix(df, brackets):
    matrix = {}
    for tier_name, elo_min, elo_max in ELO_TIERS:
        tier_df = df[(df['player_elo'] >= elo_min) & (df['player_elo'] <= elo_max)] if not df.empty else pd.DataFrame()
        matrix[tier_name] = {}
        for b in brackets:
            if not tier_df.empty:
                b_df = tier_df[tier_df['time_scramble_bracket'] == b]
                times = b_df['reaction_time'].values if not b_df.empty else np.array([])
                n = len(times)
                avg_ro = float(np.mean(times)) if n > 0 else 0.0
            else:
                times = np.array([])
                n, avg_ro = 0, 0.0
            matrix[tier_name][b] = {
                'n': n,
                'avg_ro': avg_ro if pd.notna(avg_ro) else 0.0,
                'times': times
            }
    return matrix

def print_ro_matrix(label, matrix, brackets):
    for tier_name, _, _ in ELO_TIERS:
        tier_total_n = sum(data['n'] for data in matrix[tier_name].values())
        print(f'\n--- {label} R_O: {tier_name} Elo (Valid Games N = {tier_total_n}) ---')
        print(f'{"Bracket":<20} {"N":>8} {"Avg R_O (s)":>12}')
        print('-' * 42)
        for b in brackets:
            n = matrix[tier_name][b]['n']
            avg_ro = matrix[tier_name][b]['avg_ro']
            print(f'{b:<20} {n:>8} {avg_ro:>11.2f}s')

def compute_welch_stats(x1, x2):
    """
    Computes Welch's t-test and 95% Confidence Interval for difference in means (mean1 - mean2).
    x1: CRISC reaction times array
    x2: Baseline reaction times array
    """
    n1, n2 = len(x1), len(x2)
    if n1 < 2 or n2 < 2:
        return 0.0, 0.0, 0.0, "ns"

    m1, m2 = float(np.mean(x1)), float(np.mean(x2))
    v1, v2 = float(np.var(x1, ddof=1)), float(np.var(x2, ddof=1))
    
    diff = m1 - m2
    se = math.sqrt((v1 / n1) + (v2 / n2))
    
    if se == 0:
        return diff, 0.0, 0.0, "ns"

    ci_lower = diff - 1.96 * se
    ci_upper = diff + 1.96 * se
    
    z = abs(diff) / se
    if z >= 3.291:
        sig = "***"
    elif z >= 2.576:
        sig = "**"
    elif z >= 1.960:
        sig = "*"
    else:
        sig = "ns"
        
    return diff, ci_lower, ci_upper, sig

crisc_csv = f"./true_criscs/true_criscs_{crisc_path_id}.csv"

print(f"\nComputing Pooled Stratified Reaction Time (R_O) across months: {months}...")

crisc_records_list = []
baseline_records_list = []

for m in months:
    parquet_path = f"{data_dir}/aix_lichess_{m}_low.parquet"
    baseline_csv = f"./baseline_moves/baseline_moves_{m}.csv"
    
    if os.path.exists(parquet_path):
        c_rec = compute_ro_records(crisc_csv, parquet_path)
        if not c_rec.empty:
            crisc_records_list.append(c_rec)
            
        b_rec = compute_ro_records(baseline_csv, parquet_path)
        if not b_rec.empty:
            baseline_records_list.append(b_rec)

crisc_df = pd.concat(crisc_records_list, ignore_index=True) if crisc_records_list else pd.DataFrame()
baseline_df = pd.concat(baseline_records_list, ignore_index=True) if baseline_records_list else pd.DataFrame()

# Derive brackets dynamically or fallback
if not crisc_df.empty and 'time_scramble_bracket' in crisc_df.columns:
    brackets = sorted(
        crisc_df['time_scramble_bracket'].dropna().unique(),
        key=lambda b: int(b.split('vs')[1].strip().lstrip('<=').split('s')[0].split('-')[0])
    )
else:
    brackets = ['<=5s vs <=5s', '<=5s vs 5-10s', '<=5s vs 10-15s', '<=5s vs 15-20s']

crisc_ro_matrix = build_ro_matrix(crisc_df, brackets)
baseline_ro_matrix = build_ro_matrix(baseline_df, brackets)

print("\n========================================")
print("CRISC OPPONENT REACTION TIME (R_O)")
print("========================================")
print_ro_matrix("CRISC", crisc_ro_matrix, brackets)

print("\n========================================")
print("BASELINE OPPONENT REACTION TIME (R_O)")
print("========================================")
print_ro_matrix("BASELINE", baseline_ro_matrix, brackets)

# Print Reaction Time Difference Matrix (CRISC R_O minus Baseline R_O)
col_width = 20
print("\n========================================")
print("REACTION TIME DIFFERENCE ΔR_O (CRISC minus BASELINE)")
print("========================================")
print(f'\n{"Elo Tier":<15}', end='')
for b in brackets:
    print(f'{b:>{col_width}}', end='')
print()
print('-' * (15 + col_width * len(brackets)))
for tier_name, _, _ in ELO_TIERS:
    print(f'{tier_name:<15}', end='')
    for b in brackets:
        crisc_ro = crisc_ro_matrix[tier_name][b]['avg_ro']
        baseline_ro = baseline_ro_matrix[tier_name][b]['avg_ro']
        diff = crisc_ro - baseline_ro
        print(f'{diff:>+{col_width - 1}.2f}s', end='')
    print()

print("\n========================================================================================================")
print("REACTION TIME DIFFERENCE & STATISTICAL SIGNIFICANCE (Welch's t-Test & 95% CI)")
print("Legend: *** (p < 0.001), ** (p < 0.01), * (p < 0.05), ns (not significant)")
print("========================================================================================================")

for tier_name, _, _ in ELO_TIERS:
    print(f"\n--- {tier_name} Elo ---")
    for b in brackets:
        x1 = crisc_ro_matrix[tier_name][b]['times']
        x2 = baseline_ro_matrix[tier_name][b]['times']
        diff, ci_l, ci_u, sig = compute_welch_stats(x1, x2)
        print(f"{b:<20}: {diff:>+6.2f}s{sig:<4} (95% CI: [{ci_l:>+6.2f}s, {ci_u:>+6.2f}s])")
