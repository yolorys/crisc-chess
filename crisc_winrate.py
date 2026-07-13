import pandas as pd
import sys

if len(sys.argv) < 2:
    print("Usage: python crisc_winrate.py <MONTH>")
    sys.exit(1)

month = sys.argv[1]

print("Calculating Global CRISC Win Rate ...")

# 1. Load the finalized CRISC dataset
df = pd.read_csv(f'./true_criscs/true_criscs_{month}.csv')
total_criscs = len(df)

if total_criscs == 0:
    print("Dataset is empty. No CRISCs to analyze.")
    exit()

# 2. Filter for games where the player who executed the CRISC actually won
# '1-0' means White won, '0-1' means Black won
white_wins = df[(df['crisc_player'] == 'White') & (df['result'] == '1-0')]
black_wins = df[(df['crisc_player'] == 'Black') & (df['result'] == '0-1')]

total_wins = len(white_wins) + len(black_wins)

# 3. Calculate the percentage
win_rate = (total_wins / total_criscs) * 100

print(f"Total True CRISCs analyzed: {total_criscs}")
print(f"Total games WON after executing a CRISC: {total_wins}")
print(f"\n--- GLOBAL CRISC WIN RATE ---")
print(f"{win_rate:.2f}%\n")
