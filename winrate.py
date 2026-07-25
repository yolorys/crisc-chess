import pandas as pd
import sys
import os

if len(sys.argv) < 3:
    print("Usage: python winrate.py <CRISC_PATH_ID> <month1> [month2 ...]")
    sys.exit(1)

crisc_path_id = sys.argv[1]
months = sys.argv[2:]

ELO_TIERS = [
    ('< 1000', 0, 999),
    ('1000 - 1500', 1000, 1500),
    ('1500 - 2000', 1500, 2000),
    ('> 2000', 2000, 9999)
]

def compute_win_rate(dataframe):
    total = len(dataframe)
    if total == 0:
        return 0, 0.0
    player_col = 'player' if 'player' in dataframe.columns else 'crisc_player'
    white_wins = len(dataframe[(dataframe[player_col] == 'White') & (dataframe['result'] == '1-0')])
    black_wins = len(dataframe[(dataframe[player_col] == 'Black') & (dataframe['result'] == '0-1')])
    return total, (white_wins + black_wins) / total * 100

def build_win_rate_matrix(df, brackets):
    matrix = {}
    elo_col = 'player_elo' if 'player_elo' in df.columns else 'attacker_elo'
    for tier_name, elo_min, elo_max in ELO_TIERS:
        tier_df = df[(df[elo_col] >= elo_min) & (df[elo_col] <= elo_max)]
        matrix[tier_name] = {}
        for b in brackets:
            n, wr = compute_win_rate(tier_df[tier_df['time_scramble_bracket'] == b])
            matrix[tier_name][b] = (n, wr)
    return matrix

def print_matrix(label, matrix, brackets):
    for tier_name, _, _ in ELO_TIERS:
        tier_total = sum(n for n, _ in matrix[tier_name].values())
        print(f'\n--- {label}: {tier_name} Elo (N = {tier_total}) ---')
        print(f'{"Bracket":<20} {"N":>8} {"Win Rate":>10}')
        print('-' * 40)
        for b in brackets:
            n, wr = matrix[tier_name][b]
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
        lift = crisc_matrix[tier_name][b][1] - baseline_matrix[tier_name][b][1]
        print(f'{lift:>+{col_width - 1}.2f}%', end='')
    print()
