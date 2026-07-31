import argparse
import os
import duckdb
import pandas as pd
import plotly.graph_objects as go

parser = argparse.ArgumentParser(description="3D CRISC Reaction Time Scatter Plot")
parser.add_argument("--months", nargs="+", required=True, help="List of months (e.g. 2026-02 2026-03 2026-04)")
parser.add_argument("--perm", default="T5_E400", help="Permutation ID (default: T5_E400)")
parser.add_argument("--data", default="./data", help="Data directory containing Parquet files")
args = parser.parse_args()

months = args.months
perm = args.perm
data_dir = args.data

month_id = months[0] if len(months) == 1 else f"{months[0]}~{months[-1]}"
crisc_path_id = f"{month_id}_{perm}"
crisc_csv = f"./true_criscs/true_criscs_{crisc_path_id}.csv"

os.makedirs("./visuals", exist_ok=True)

print(f"\nLoading CRISC data from: {crisc_csv}")
print(f"Joining against Parquet files in: {data_dir}")

all_records = []

for m in months:
    parquet_path = f"{data_dir}/aix_lichess_{m}_low.parquet"
    if not os.path.exists(parquet_path):
        print(f"  [SKIP] {parquet_path} not found")
        continue

    print(f"  Processing {m}...")

    con = duckdb.connect()
    con.execute(f"CREATE TABLE crisc AS SELECT * FROM read_csv_auto('{crisc_csv}')")

    results = con.execute(f"""
        SELECT
            c.lichess_id,
            c.ply,
            c.result,
            c.player,
            c.player_elo,
            p.clocks_white,
            p.clocks_black
        FROM crisc c
        JOIN '{parquet_path}' p ON c.lichess_id = p.lichess_id
    """).df()
    con.close()

    for _, row in results.iterrows():
        ply = int(row['ply'])
        player = row['player']
        result_raw = row['result']
        clocks_white = row['clocks_white']
        clocks_black = row['clocks_black']

        try:
            move_index = ply // 2

            if player == 'White':
                t_p = int(clocks_white[move_index])        # Player clock after delivering a CRISC
                t_o_before = int(clocks_black[move_index - 1])  # Opponent clock before responding
                t_o_after = int(clocks_black[move_index])       # Opponent clock after responding
            else:
                t_p = int(clocks_black[move_index - 1])
                t_o_before = int(clocks_white[move_index - 1])
                t_o_after = int(clocks_white[move_index])

            r_o = t_o_before - t_o_after  # Reaction time in seconds

            # Filter premoves and server lag underflow artifacts
            if r_o <= 0:
                continue
            # T_O (opponent clock at CRISC) is t_o_before
            t_o = t_o_before

            # Determine outcome from the CRISC player's perspective
            if result_raw == '1-0':
                outcome = 'Win' if player == 'White' else 'Loss'
            elif result_raw == '0-1':
                outcome = 'Win' if player == 'Black' else 'Loss'
            else:
                outcome = 'Draw'

            all_records.append({
                'lichess_id': row['lichess_id'],
                'ply': ply,
                'T_O': t_o,
                'T_P': t_p,
                'R_O': r_o,
                'player_elo': int(row['player_elo']),
                'outcome': outcome,
            })

        except Exception:
            continue

df = pd.DataFrame(all_records)
print(f"\nTotal valid data points: {len(df)}")

# Map outcomes to colors
color_map = {'Win': '#22c55e', 'Loss': '#ef4444', 'Draw': '#eab308'}
df['color'] = df['outcome'].map(color_map)

traces = []
for outcome in ['Win', 'Loss', 'Draw']:
    sub = df[df['outcome'] == outcome]
    traces.append(go.Scatter3d(
        x=sub['T_O'],
        y=sub['T_P'],
        z=sub['R_O'],
        mode='markers',
        name=outcome,
        marker=dict(
            size=3,
            color=color_map[outcome],
            opacity=0.45,
        ),
        customdata=sub[['lichess_id', 'ply', 'player_elo']].values,
        hovertemplate=(
            "<b>%{fullData.name}</b><br>"
            "T_O (Opponent clock): %{x}s<br>"
            "T_P (Player clock): %{y}s<br>"
            "R_O (reaction time): %{z}s<br>"
            "Elo: %{customdata[2]}<br>"
            "Position: lichess.org/%{customdata[0]}#%{customdata[1]}<br>"
            "<extra></extra>"
        )
    ))

fig = go.Figure(data=traces)

fig.update_layout(
    title=dict(
        text=f"Opponent Reaction Time (R_O) vs Clock Time — {month_id} | N={len(df):,} events",
        font=dict(size=16)
    ),
    scene=dict(
        xaxis=dict(title="T_O — Opponent Clock (s)", range=[0, 5]),
        yaxis=dict(title="T_P — Player Clock (s)", range=[0, 20]),
        zaxis=dict(title="R_O — Reaction Time (s)", range=[0, 5]),
        bgcolor='rgb(15, 15, 25)',
        xaxis_backgroundcolor='rgb(15, 15, 25)',
        yaxis_backgroundcolor='rgb(15, 15, 25)',
        zaxis_backgroundcolor='rgb(15, 15, 25)',
    ),
    paper_bgcolor='rgb(15, 15, 25)',
    plot_bgcolor='rgb(15, 15, 25)',
    font=dict(color='white'),
    legend=dict(
        title="Outcome (from CRISC Player's perspective)",
        font=dict(color='white'),
        bgcolor='rgba(255,255,255,0.05)',
    ),
    margin=dict(l=0, r=0, b=0, t=50),
)

output_path = f"./visuals/reaction_3d_{crisc_path_id}.html"
fig.write_html(output_path)
print(f"\nPlot saved to: {output_path}")
print("Open it in any browser to explore interactively.")
