import pandas as pd
import os

def compute_win_stats(dataframe):
    total = len(dataframe)
    white_wins = len(dataframe[(dataframe['risck_player'] == 'White') & (dataframe['result'] == '1-0')])
    black_wins = len(dataframe[(dataframe['risck_player'] == 'Black') & (dataframe['result'] == '0-1')])
    total_wins = white_wins + black_wins
    win_rate = (total_wins / total) * 100 if total > 0 else 0
    return white_wins, black_wins, total_wins, win_rate

months = ['2026-02', '2026-03', '2026-04']

dfs = []
per_month_wr = {}
for m in months:
    month_df = pd.read_csv(f'./control_checks/control_checks_{m}.csv')
    dfs.append(month_df)
    _, _, _, m_win_rate = compute_win_stats(month_df)
    per_month_wr[m] = f'{m_win_rate:.2f}%'

df = pd.concat(dfs, ignore_index=True)

white_wins, black_wins, total_wins, win_rate = compute_win_stats(df)

print(f'Total Control Games: {len(df)}')
print(f'White Check -> White Win: {white_wins}')
print(f'Black Check -> Black Win: {black_wins}')
print(f'Total Wins by Checking Player: {total_wins}')
print(f'')
print(f'--- CONTROL GROUP WIN RATE ---')
print(f'{win_rate:.2f}%')

# Write Win_Rate column to control_group_results_T5.csv (per-month + combined)
results_path = './results/control_group_results_T5.csv'
if os.path.exists(results_path):
    ctrl_df = pd.read_csv(results_path)

    # Write per-month and combined win rates
    ctrl_df['Win_Rate'] = ctrl_df['Month'].map(per_month_wr)
    ctrl_df.loc[ctrl_df['Month'] == 'ALL_MONTHS_COMBINED', 'Win_Rate'] = f'{win_rate:.2f}%'
    ctrl_df.to_csv(results_path, index=False)
    print(f'Win rates saved to {results_path}')
