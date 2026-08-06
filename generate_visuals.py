import argparse
import math
import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns
import duckdb

# Configure modern, elegant typography and canvas defaults
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
plt.rcParams['axes.edgecolor'] = '#CBD5E1'
plt.rcParams['axes.linewidth'] = 0.8
plt.rcParams['axes.labelsize'] = 10
plt.rcParams['axes.titlesize'] = 11
plt.rcParams['xtick.labelsize'] = 9
plt.rcParams['ytick.labelsize'] = 9
plt.rcParams['legend.fontsize'] = 9

# Curated Professional Academic Color Palette
COLOR_CRISC = '#1E3A8A'       # Deep Royal Navy
COLOR_BASELINE = '#94A3B8'    # Slate Gray
COLOR_ACCENT = '#991B1B'      # Muted Deep Crimson
COLOR_TEAL = '#0F766E'        # Deep Teal
COLOR_INDIGO = '#4338CA'      # Deep Indigo
COLOR_AMBER = '#D97706'       # Deep Amber

# Heatmap Colormaps
CMAP_WINRATE = sns.color_palette("mako", as_cmap=True)
CMAP_REACTION = sns.color_palette("crest_r", as_cmap=True)

ELO_TIERS = [
    ('< 1000', 0, 999),
    ('1000 - 1500', 1000, 1500),
    ('1500 - 2000', 1500, 2000),
    ('> 2000', 2000, 9999)
]

BRACKETS = ['<=5s vs <=5s', '<=5s vs 5-10s', '<=5s vs 10-15s', '<=5s vs 15-20s']

def compute_win_rate(dataframe):
    total = len(dataframe)
    if total == 0:
        return 0, 0, 0.0
    player_col = 'player' if 'player' in dataframe.columns else 'crisc_player'
    white_wins = len(dataframe[(dataframe[player_col] == 'White') & (dataframe['result'] == '1-0')])
    black_wins = len(dataframe[(dataframe[player_col] == 'Black') & (dataframe['result'] == '0-1')])
    wins = white_wins + black_wins
    return total, wins, (wins / total * 100.0)

def build_win_rate_matrix(df):
    matrix = {}
    elo_col = 'player_elo' if 'player_elo' in df.columns else 'attacker_elo'
    for tier_name, elo_min, elo_max in ELO_TIERS:
        tier_df = df[(df[elo_col] >= elo_min) & (df[elo_col] <= elo_max)]
        matrix[tier_name] = {}
        for b in BRACKETS:
            n, w, wr = compute_win_rate(tier_df[tier_df['time_scramble_bracket'] == b])
            matrix[tier_name][b] = (n, w, wr)
    return matrix

def compute_winrate_inferential_stats(n1, w1, n2, w2):
    if n1 == 0 or n2 == 0:
        return 0.0, 0.0, 0.0, "ns"
    p1 = w1 / n1
    p2 = w2 / n2
    lift = (p1 - p2) * 100.0
    se = math.sqrt((p1 * (1.0 - p1) / n1) + (p2 * (1.0 - p2) / n2))
    ci_lower = lift - (1.96 * se * 100.0)
    ci_upper = lift + (1.96 * se * 100.0)

    p_pool = (w1 + w2) / (n1 + n2)
    se_pool = math.sqrt(p_pool * (1.0 - p_pool) * ((1.0 / n1) + (1.0 / n2)))
    z = abs(p1 - p2) / se_pool if se_pool > 0 else 0.0

    if z >= 3.2905:
        sig = "***"
    elif z >= 2.5758:
        sig = "**"
    elif z >= 1.9600:
        sig = "*"
    else:
        sig = "ns"

    return lift, ci_lower, ci_upper, sig

def compute_ro_records(csv_path, parquet_path):
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
                time_before = int(clocks_black[move_index - 1])
                time_after = int(clocks_black[move_index])
            else:
                time_before = int(clocks_white[move_index - 1])
                time_after = int(clocks_white[move_index])

            reaction_time = time_before - time_after
            if reaction_time > 0:
                valid_records.append({
                    'reaction_time': reaction_time,
                    'player_elo': int(row['player_elo']),
                    'time_scramble_bracket': row['time_scramble_bracket']
                })
        except Exception:
            continue

    return pd.DataFrame(valid_records)

def build_ro_matrix(df):
    matrix = {}
    for tier_name, elo_min, elo_max in ELO_TIERS:
        tier_df = df[(df['player_elo'] >= elo_min) & (df['player_elo'] <= elo_max)] if not df.empty else pd.DataFrame()
        matrix[tier_name] = {}
        for b in BRACKETS:
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

def compute_welch_stats(x1, x2):
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

def generate_visualizations(months, perm, data_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    month_id = months[0] if len(months) == 1 else f"{months[0]}~{months[-1]}"
    crisc_path_id = f"{month_id}_{perm}"

    crisc_csv = f"./true_criscs/true_criscs_{crisc_path_id}.csv"
    crisc_df = pd.read_csv(crisc_csv) if os.path.exists(crisc_csv) else pd.DataFrame()

    baseline_dfs = []
    for m in months:
        b_path = f"./baseline_moves/baseline_moves_{m}.csv"
        if os.path.exists(b_path):
            baseline_dfs.append(pd.read_csv(b_path))
    baseline_df = pd.concat(baseline_dfs, ignore_index=True) if baseline_dfs else pd.DataFrame()

    crisc_wr_matrix = build_win_rate_matrix(crisc_df)
    baseline_wr_matrix = build_win_rate_matrix(baseline_df)

    crisc_ro_list = []
    baseline_ro_list = []
    for m in months:
        p_path = f"{data_dir}/aix_lichess_{m}_low.parquet"
        b_csv = f"./baseline_moves/baseline_moves_{m}.csv"
        if os.path.exists(p_path):
            c_rec = compute_ro_records(crisc_csv, p_path)
            if not c_rec.empty:
                crisc_ro_list.append(c_rec)
            b_rec = compute_ro_records(b_csv, p_path)
            if not b_rec.empty:
                baseline_ro_list.append(b_rec)

    crisc_ro_df = pd.concat(crisc_ro_list, ignore_index=True) if crisc_ro_list else pd.DataFrame()
    baseline_ro_df = pd.concat(baseline_ro_list, ignore_index=True) if baseline_ro_list else pd.DataFrame()

    crisc_ro_matrix = build_ro_matrix(crisc_ro_df)
    baseline_ro_matrix = build_ro_matrix(baseline_ro_df)

    tier_labels = [t[0] for t in ELO_TIERS]

    # -------------------------------------------------------------
    # Figure 1: Heatmap of Win Rate Lift & Equal-Scramble Bar Chart
    # -------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={'width_ratios': [1.2, 1]})

    # Panel A: Heatmap of Win Rate Lift (ΔW) with Mako Palette
    lift_data = np.zeros((len(ELO_TIERS), len(BRACKETS)))
    annot_data = []

    for i, (tier_name, _, _) in enumerate(ELO_TIERS):
        row_annot = []
        for j, b in enumerate(BRACKETS):
            n1, w1, _ = crisc_wr_matrix[tier_name][b]
            n2, w2, _ = baseline_wr_matrix[tier_name][b]
            lift, ci_l, ci_u, sig = compute_winrate_inferential_stats(n1, w1, n2, w2)
            lift_data[i, j] = lift
            sign_str = f"+{lift:.2f}%" if lift >= 0 else f"{lift:.2f}%"
            row_annot.append(f"{sign_str}{sig}\n[{ci_l:+.1f}%, {ci_u:+.1f}%]")
        annot_data.append(row_annot)

    sns.heatmap(lift_data, annot=np.array(annot_data), fmt='', cmap=CMAP_WINRATE,
                cbar_kws={'label': 'Win Rate Lift ΔW (%)'},
                yticklabels=tier_labels, xticklabels=BRACKETS, ax=axes[0],
                annot_kws={'size': 9, 'weight': 'bold', 'color': '#FFFFFF'},
                linewidths=0.5, linecolor='#F1F5F9')
    axes[0].set_title('A. Win Rate Lift ΔW Matrix by Elo Tier & Scramble Bracket', fontsize=11, fontweight='bold', pad=12)
    axes[0].set_ylabel('Player Elo Tier', fontsize=10, fontweight='bold')
    axes[0].set_xlabel('Time Scramble Bracket (Player vs Opponent Clock)', fontsize=10, fontweight='bold')

    # Panel B: Equal Scramble Win Rate Comparison (<=5s vs <=5s)
    x = np.arange(len(tier_labels))
    width = 0.35

    crisc_wrs = [crisc_wr_matrix[t[0]]['<=5s vs <=5s'][2] for t in ELO_TIERS]
    baseline_wrs = [baseline_wr_matrix[t[0]]['<=5s vs <=5s'][2] for t in ELO_TIERS]

    rects1 = axes[1].bar(x - width/2, crisc_wrs, width, label='CRISC', color=COLOR_CRISC, edgecolor='none')
    rects2 = axes[1].bar(x + width/2, baseline_wrs, width, label='Baseline', color=COLOR_BASELINE, edgecolor='none')

    axes[1].set_ylabel('Observed Win Rate (%)', fontsize=10, fontweight='bold')
    axes[1].set_title('B. Equal Time Scramble Win Rate (<=5s vs <=5s)', fontsize=11, fontweight='bold', pad=12)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(tier_labels)
    axes[1].legend(frameon=True, facecolor='#FFFFFF', edgecolor='none')
    axes[1].set_ylim(0, 100)
    axes[1].set_xlabel('Player Elo Tier', fontsize=10, fontweight='bold')
    axes[1].yaxis.grid(True, linestyle='--', alpha=0.5, color='#CBD5E1')
    axes[1].set_axisbelow(True)

    for rect in rects1:
        height = rect.get_height()
        axes[1].annotate(f'{height:.1f}%',
                         xy=(rect.get_x() + rect.get_width() / 2, height),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=8, fontweight='bold', color=COLOR_CRISC)
    for rect in rects2:
        height = rect.get_height()
        axes[1].annotate(f'{height:.1f}%',
                         xy=(rect.get_x() + rect.get_width() / 2, height),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=8, color='#475569')

    plt.tight_layout()
    fig1_path = os.path.join(output_dir, 'fig1_winrate_analysis.png')
    plt.savefig(fig1_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved Figure 1 to: {fig1_path}")

    # -------------------------------------------------------------
    # Figure 2: Opponent Reaction Time Analysis (R_O & ΔR_O)
    # -------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={'width_ratios': [1.2, 1]})

    # Panel A: Heatmap of Reaction Time Difference (ΔR_O) with Crest Colormap
    ro_diff_data = np.zeros((len(ELO_TIERS), len(BRACKETS)))
    ro_annot_data = []

    for i, (tier_name, _, _) in enumerate(ELO_TIERS):
        row_annot = []
        for j, b in enumerate(BRACKETS):
            x1 = crisc_ro_matrix[tier_name][b]['times']
            x2 = baseline_ro_matrix[tier_name][b]['times']
            diff, ci_l, ci_u, sig = compute_welch_stats(x1, x2)
            ro_diff_data[i, j] = diff
            row_annot.append(f"{diff:+.2f}s{sig}\n[{ci_l:+.2f}s, {ci_u:+.2f}s]")
        ro_annot_data.append(row_annot)

    sns.heatmap(ro_diff_data, annot=np.array(ro_annot_data), fmt='', cmap=CMAP_REACTION,
                cbar_kws={'label': 'Reaction Time Difference ΔR_O (seconds)'},
                yticklabels=tier_labels, xticklabels=BRACKETS, ax=axes[0],
                annot_kws={'size': 9, 'weight': 'bold', 'color': '#FFFFFF'},
                linewidths=0.5, linecolor='#F1F5F9')
    axes[0].set_title('A. Reaction Time Difference ΔR_O Matrix (CRISC minus Baseline)', fontsize=11, fontweight='bold', pad=12)
    axes[0].set_ylabel('Player Elo Tier', fontsize=10, fontweight='bold')
    axes[0].set_xlabel('Time Scramble Bracket (Player vs Opponent Clock)', fontsize=10, fontweight='bold')

    # Panel B: Absolute Opponent Reaction Times in Equal Scramble (<=5s vs <=5s)
    crisc_ros = [crisc_ro_matrix[t[0]]['<=5s vs <=5s']['avg_ro'] for t in ELO_TIERS]
    baseline_ros = [baseline_ro_matrix[t[0]]['<=5s vs <=5s']['avg_ro'] for t in ELO_TIERS]

    rects1 = axes[1].bar(x - width/2, crisc_ros, width, label='Post-CRISC', color=COLOR_TEAL, edgecolor='none')
    rects2 = axes[1].bar(x + width/2, baseline_ros, width, label='Post-Baseline', color=COLOR_BASELINE, edgecolor='none')

    axes[1].set_ylabel('Mean Opponent Reaction Time R_O (seconds)', fontsize=10, fontweight='bold')
    axes[1].set_title('B. Equal Scramble Opponent Reaction Time (<=5s vs <=5s)', fontsize=11, fontweight='bold', pad=12)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(tier_labels)
    axes[1].legend(frameon=True, facecolor='#FFFFFF', edgecolor='none')
    axes[1].set_ylim(0, 2.0)
    axes[1].set_xlabel('Player Elo Tier', fontsize=10, fontweight='bold')
    axes[1].yaxis.grid(True, linestyle='--', alpha=0.5, color='#CBD5E1')
    axes[1].set_axisbelow(True)

    for rect in rects1:
        height = rect.get_height()
        axes[1].annotate(f'{height:.2f}s',
                         xy=(rect.get_x() + rect.get_width() / 2, height),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=8, fontweight='bold', color=COLOR_TEAL)
    for rect in rects2:
        height = rect.get_height()
        axes[1].annotate(f'{height:.2f}s',
                         xy=(rect.get_x() + rect.get_width() / 2, height),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=8, color='#475569')

    plt.tight_layout()
    fig2_path = os.path.join(output_dir, 'fig2_reaction_time_analysis.png')
    plt.savefig(fig2_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved Figure 2 to: {fig2_path}")

    # -------------------------------------------------------------
    # Figure 3: Research Summary Dashboard (Refined Academic Palette)
    # -------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Panel A: Win Rate Lift across Elo for Equal Scramble
    lift_eq = [lift_data[i, 0] for i in range(len(ELO_TIERS))]
    ci_eq = []
    for i, (tier_name, _, _) in enumerate(ELO_TIERS):
        n1, w1, _ = crisc_wr_matrix[tier_name]['<=5s vs <=5s']
        n2, w2, _ = baseline_wr_matrix[tier_name]['<=5s vs <=5s']
        _, ci_l, ci_u, _ = compute_winrate_inferential_stats(n1, w1, n2, w2)
        ci_eq.append((ci_u - ci_l) / 2.0)

    axes[0, 0].errorbar(tier_labels, lift_eq, yerr=ci_eq, fmt='o-', color=COLOR_CRISC, ecolor=COLOR_CRISC,
                        elinewidth=2, capsize=5, capthick=2, markersize=7)
    axes[0, 0].axhline(0, color='#94A3B8', linestyle='--', linewidth=0.8)
    axes[0, 0].set_title('A. Win Rate Lift ΔW in Equal Scrambles (95% CI)', fontsize=11, fontweight='bold')
    axes[0, 0].set_ylabel('Win Rate Lift ΔW (%)', fontsize=10, fontweight='bold')
    axes[0, 0].set_xlabel('Player Elo Tier', fontsize=10, fontweight='bold')
    axes[0, 0].set_ylim(-5, 15)
    axes[0, 0].yaxis.grid(True, linestyle='--', alpha=0.5, color='#CBD5E1')
    axes[0, 0].set_axisbelow(True)

    # Panel B: Reaction Time Reduction across Elo for Equal Scramble
    ro_diff_eq = [ro_diff_data[i, 0] for i in range(len(ELO_TIERS))]
    ro_ci_eq = []
    for i, (tier_name, _, _) in enumerate(ELO_TIERS):
        x1 = crisc_ro_matrix[tier_name]['<=5s vs <=5s']['times']
        x2 = baseline_ro_matrix[tier_name]['<=5s vs <=5s']['times']
        _, ci_l, ci_u, _ = compute_welch_stats(x1, x2)
        ro_ci_eq.append((ci_u - ci_l) / 2.0)

    axes[0, 1].errorbar(tier_labels, ro_diff_eq, yerr=ro_ci_eq, fmt='s-', color=COLOR_ACCENT, ecolor=COLOR_ACCENT,
                        elinewidth=2, capsize=5, capthick=2, markersize=7)
    axes[0, 1].axhline(0, color='#94A3B8', linestyle='--', linewidth=0.8)
    axes[0, 1].set_title('B. Opponent Reaction Time Diff ΔR_O in Equal Scrambles (95% CI)', fontsize=11, fontweight='bold')
    axes[0, 1].set_ylabel('Reaction Time Diff ΔR_O (seconds)', fontsize=10, fontweight='bold')
    axes[0, 1].set_xlabel('Player Elo Tier', fontsize=10, fontweight='bold')
    axes[0, 1].set_ylim(-0.35, 0.1)
    axes[0, 1].yaxis.grid(True, linestyle='--', alpha=0.5, color='#CBD5E1')
    axes[0, 1].set_axisbelow(True)

    # Panel C: Sample Sizes per Elo Tier
    crisc_sample_sizes = [sum(crisc_wr_matrix[t[0]][b][0] for b in BRACKETS) for t in ELO_TIERS]
    baseline_sample_sizes = [sum(baseline_wr_matrix[t[0]][b][0] for b in BRACKETS) for t in ELO_TIERS]

    axes[1, 0].bar(x - width/2, crisc_sample_sizes, width, label='CRISC (N = 10,813)', color=COLOR_TEAL, edgecolor='none')
    axes[1, 0].bar(x + width/2, baseline_sample_sizes, width, label='Baseline (N = 64,500)', color=COLOR_BASELINE, edgecolor='none')
    axes[1, 0].set_title('C. Sample Event Counts (N) by Elo Tier', fontsize=11, fontweight='bold')
    axes[1, 0].set_ylabel('Total Moves Evaluated (N)', fontsize=10, fontweight='bold')
    axes[1, 0].set_xticks(x)
    axes[1, 0].set_xticklabels(tier_labels)
    axes[1, 0].legend(frameon=True, facecolor='#FFFFFF', edgecolor='none')
    axes[1, 0].set_xlabel('Player Elo Tier', fontsize=10, fontweight='bold')
    axes[1, 0].yaxis.grid(True, linestyle='--', alpha=0.5, color='#CBD5E1')
    axes[1, 0].set_axisbelow(True)

    # Panel D: Win Rate Lift across Clock Asymmetry Brackets
    tier_colors = [COLOR_CRISC, COLOR_TEAL, COLOR_INDIGO, COLOR_ACCENT]
    tier_markers = ['o', 's', '^', 'd']

    for i, (tier_name, _, _) in enumerate(ELO_TIERS):
        lifts_by_b = [lift_data[i, j] for j in range(len(BRACKETS))]
        axes[1, 1].plot(BRACKETS, lifts_by_b, marker=tier_markers[i], color=tier_colors[i], label=tier_name, linewidth=1.8)

    axes[1, 1].axhline(0, color='#94A3B8', linestyle='--', linewidth=0.8)
    axes[1, 1].set_title('D. Win Rate Lift ΔW Across Scramble Clock Brackets', fontsize=11, fontweight='bold')
    axes[1, 1].set_ylabel('Win Rate Lift ΔW (%)', fontsize=10, fontweight='bold')
    axes[1, 1].set_xlabel('Time Scramble Bracket', fontsize=10, fontweight='bold')
    axes[1, 1].legend(title='Elo Tier', frameon=True, facecolor='#FFFFFF', edgecolor='none')
    axes[1, 1].tick_params(axis='x', rotation=15)
    axes[1, 1].yaxis.grid(True, linestyle='--', alpha=0.5, color='#CBD5E1')
    axes[1, 1].set_axisbelow(True)

    plt.tight_layout()
    fig3_path = os.path.join(output_dir, 'fig3_research_summary_dashboard.png')
    plt.savefig(fig3_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved Figure 3 to: {fig3_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate CRISC Visualizations")
    parser.add_argument("--months", nargs="+", default=["2026-02", "2026-03", "2026-04"], help="Months analyzed")
    parser.add_argument("--perm", default="T5_E400", help="Permutation ID")
    parser.add_argument("--data", default="./data", help="Data directory")
    parser.add_argument("--output", default="./visuals", help="Output directory for figures")
    args = parser.parse_args()

    generate_visualizations(args.months, args.perm, args.data, args.output)
