import argparse
import math
import os
import sys
import pandas as pd

parser = argparse.ArgumentParser(description="CRISC & Baseline Win Rate Analysis")
parser.add_argument("--months", nargs="+", required=True, help="List of months (e.g. 2026-02 2026-03 2026-04)")
parser.add_argument("--perm", default="T5_E400", help="Permutation ID (default: T5_E400)")
args = parser.parse_args()

months = args.months
perm = args.perm

month_id = months[0] if len(months) == 1 else f"{months[0]}~{months[-1]}"
crisc_path_id = f"{month_id}_{perm}"

ELO_TIERS = [
    ('< 1000', 0, 999),
    ('1000 - 1500', 1000, 1500),
    ('1500 - 2000', 1500, 2000),
    ('> 2000', 2000, 9999)
]

def compute_win_rate(dataframe):
    total = len(dataframe)
    if total == 0:
        return 0, 0, 0.0
    player_col = 'player' if 'player' in dataframe.columns else 'crisc_player'
    white_wins = len(dataframe[(dataframe[player_col] == 'White') & (dataframe['result'] == '1-0')])
    black_wins = len(dataframe[(dataframe[player_col] == 'Black') & (dataframe['result'] == '0-1')])
    wins = white_wins + black_wins
    return total, wins, (wins / total * 100.0)

def build_win_rate_matrix(df, brackets):
    matrix = {}
    elo_col = 'player_elo' if 'player_elo' in df.columns else 'attacker_elo'
    for tier_name, elo_min, elo_max in ELO_TIERS:
        tier_df = df[(df[elo_col] >= elo_min) & (df[elo_col] <= elo_max)]
        matrix[tier_name] = {}
        for b in brackets:
            n, w, wr = compute_win_rate(tier_df[tier_df['time_scramble_bracket'] == b])
            matrix[tier_name][b] = (n, w, wr)
    return matrix

def compute_inferential_stats(n1, w1, n2, w2):
    """Computes Win Rate Lift, 95% Confidence Interval, and Chi-Square / Z-test significance."""
    if n1 == 0 or n2 == 0:
        return 0.0, 0.0, 0.0, "ns"
    p1 = w1 / n1
    p2 = w2 / n2
    lift = (p1 - p2) * 100.0

    # Standard Error of Difference between Two Proportions
    se = math.sqrt((p1 * (1.0 - p1) / n1) + (p2 * (1.0 - p2) / n2))
    ci_lower = lift - (1.96 * se * 100.0)
    ci_upper = lift + (1.96 * se * 100.0)

    # Pooled Z-test for statistical significance (equivalent to 1-DoF Chi-Square test)
    p_pool = (w1 + w2) / (n1 + n2)
    se_pool = math.sqrt(p_pool * (1.0 - p_pool) * ((1.0 / n1) + (1.0 / n2)))
    z = abs(p1 - p2) / se_pool if se_pool > 0 else 0.0

    if z >= 3.2905:
        sig = "***"  # p < 0.001
    elif z >= 2.5758:
        sig = "**"   # p < 0.01
    elif z >= 1.9600:
        sig = "*"    # p < 0.05
    else:
        sig = "ns"   # not significant

    return lift, ci_lower, ci_upper, sig

def print_matrix(label, matrix, brackets):
    for tier_name, _, _ in ELO_TIERS:
        tier_total = sum(n for n, _, _ in matrix[tier_name].values())
        print(f'\n--- {label}: {tier_name} Elo (N = {tier_total}) ---')
        print(f'{"Bracket":<20} {"N":>8} {"Win Rate":>10}')
        print('-' * 40)
        for b in brackets:
            n, _, wr = matrix[tier_name][b]
            print(f'{b:<20} {n:>8} {wr:>9.2f}%')

# Load CRISC data
crisc_path = f'./true_criscs/true_criscs_{crisc_path_id}.csv'
if not os.path.exists(crisc_path):
    print(f"Error: File {crisc_path} not found.")
    sys.exit(1)

try:
    crisc_df = pd.read_csv(crisc_path)
except (pd.errors.EmptyDataError, pd.errors.ParserError):
    crisc_df = pd.DataFrame()

print(f'Total True CRISCs Loaded: {len(crisc_df)}')

# Load baseline data — same month(s) as the CRISC extraction
baseline_dfs = []
for m in months:
    b_path = f'./baseline_moves/baseline_moves_{m}.csv'
    if os.path.exists(b_path):
        try:
            b_df = pd.read_csv(b_path)
            if not b_df.empty:
                baseline_dfs.append(b_df)
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            continue

if not baseline_dfs:
    print("Error: No valid baseline CSV files found.")
    sys.exit(1)
baseline_df = pd.concat(baseline_dfs, ignore_index=True)
print(f'Total Baseline Games Loaded: {len(baseline_df)}')

# Derive brackets dynamically from the data, or fallback to standard 4 scramble brackets
if not crisc_df.empty and 'time_scramble_bracket' in crisc_df.columns and len(crisc_df['time_scramble_bracket'].dropna()) > 0:
    brackets = sorted(
        crisc_df['time_scramble_bracket'].dropna().unique(),
        key=lambda b: int(b.split('vs')[1].strip().lstrip('<=').split('s')[0].split('-')[0])
    )
else:
    brackets = ['<=5s vs <=5s', '<=5s vs 5-10s', '<=5s vs 10-15s', '<=5s vs 15-20s']

# Build win rate matrices
crisc_matrix = build_win_rate_matrix(crisc_df, brackets)
baseline_matrix = build_win_rate_matrix(baseline_df, brackets)

# Print CRISC win rates
print("\n========================================")
print("CRISC WIN RATES")
print("========================================")
print_matrix("CRISC", crisc_matrix, brackets)

# Print baseline win rates
print("\n========================================")
print("BASELINE WIN RATES")
print("========================================")
print_matrix("BASELINE", baseline_matrix, brackets)

# Print win rate lift matrix
col_width = 20
print("\n========================================")
print("WIN RATE LIFT (CRISC minus BASELINE)")
print("========================================")
print(f'\n{"Elo Tier":<15}', end='')
for b in brackets:
    print(f'{b:>{col_width}}', end='')
print()
print('-' * (15 + col_width * len(brackets)))
for tier_name, _, _ in ELO_TIERS:
    print(f'{tier_name:<15}', end='')
    for b in brackets:
        n1, w1, wr1 = crisc_matrix[tier_name][b]
        n2, w2, wr2 = baseline_matrix[tier_name][b]
        lift = wr1 - wr2
        print(f'{lift:>+{col_width - 1}.2f}%', end='')
    print()

# Print detailed statistical significance & confidence interval table
print("\n========================================================================================================")
print("WIN RATE LIFT & STATISTICAL SIGNIFICANCE (Chi-Square / Z-Test & 95% CI)")
print("Legend: *** (p < 0.001), ** (p < 0.01), * (p < 0.05), ns (not significant)")
print("========================================================================================================")

for tier_name, _, _ in ELO_TIERS:
    print(f"\n--- {tier_name} Elo ---")
    for b in brackets:
        n1, w1, _ = crisc_matrix[tier_name][b]
        n2, w2, _ = baseline_matrix[tier_name][b]
        lift, ci_low, ci_high, sig = compute_inferential_stats(n1, w1, n2, w2)
        print(f"{b:<20}: {lift:>+6.2f}%{sig:<3}  (95% CI: [{ci_low:>+6.2f}%, {ci_high:>+6.2f}%])")

