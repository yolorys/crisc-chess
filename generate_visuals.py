import matplotlib
matplotlib.use('Agg')  # Headless backend for HPC cluster

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import os

# Create required directory structure
for folder in ["./results", "./visuals"]:
    os.makedirs(folder, exist_ok=True)

# ============================================================
# Configuration
# ============================================================
T_O_THRESHOLD = 5  # seconds — opponent time pressure threshold
sns.set_theme(style="whitegrid", font_scale=1.2)
plt.rcParams.update({
    'font.family': 'sans-serif',
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'axes.edgecolor': '#333333',
    'axes.linewidth': 0.8,
})

# Load the master scaling results
df = pd.read_csv('./results/master_scaling_results_T5_E400.csv')
combined = df[df['Month'] == 'ALL_MONTHS_COMBINED'].iloc[0]

combined_wr = float(combined['Win_Rate'].strip('%'))
combined_ro = float(combined['Reaction_Time'])
combined_n = int(combined['N'])

# Load the control group results
df_ctrl = pd.read_csv('./results/control_group_results_T5.csv')
ctrl_combined = df_ctrl[df_ctrl['Month'] == 'ALL_MONTHS_COMBINED'].iloc[0]
ctrl_ro = float(ctrl_combined['Control_Reaction_Time'])
ctrl_n_valid = int(ctrl_combined['Valid_Games'])
ctrl_n_sampled = int(ctrl_combined['Total_Sampled'])
ctrl_wr = float(ctrl_combined['Win_Rate'].strip('%')) if 'Win_Rate' in ctrl_combined and pd.notna(ctrl_combined['Win_Rate']) else None

# ============================================================
# FIGURE 1: CRISC Win Rate vs Baseline
# ============================================================
fig1, ax1 = plt.subplots(figsize=(7, 6))

categories = ['Control Check\n(Mathematically Sound Move)', 'CRISC\n']
values = [ctrl_wr, combined_wr]
colors = ['#3b82f6', '#dc2626']

bars = ax1.bar(categories, values, width=0.55, color=colors,
               edgecolor='#1e293b', linewidth=1.2, zorder=3)

# Value labels on bars
for bar, val in zip(bars, values):
    ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.2,
             f'{val:.2f}%', ha='center', va='bottom',
             fontsize=16, fontweight='bold', color='#1e293b')

ax1.set_ylabel('Win Rate (%)', fontsize=14, fontweight='bold')
ax1.set_title(f'Win Rate: Sound Checks vs. CRISC\n'
              f'($T_O \\leq {T_O_THRESHOLD}s$, $N_{{CRISC}} = {combined_n:,}$, $N_{{Control}} = {ctrl_n_sampled:,}$)',
              fontsize=14, fontweight='bold', pad=15)
ax1.set_ylim(0, 100)
ax1.tick_params(axis='both', labelsize=12)
ax1.grid(axis='y', alpha=0.3, zorder=1)
ax1.grid(axis='x', visible=False)

sns.despine(left=True, bottom=True)

fig1.savefig('./visuals/fig1_winrate.png')
plt.close(fig1)
print("Saved fig1_winrate.png")

# ============================================================
# FIGURE 2: CRISC vs Control Reaction Time
# ============================================================
fig2, ax2 = plt.subplots(figsize=(7, 6))

categories2 = ['Control Check\n(Mathematically Sound Move)', 'CRISC\n']
values2 = [ctrl_ro, combined_ro]
colors2 = ['#3b82f6', '#dc2626']

bars2 = ax2.bar(categories2, values2, width=0.55, color=colors2,
                edgecolor='#1e293b', linewidth=1.2, zorder=3)

# Value labels on bars
for bar, val in zip(bars2, values2):
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
             f'{val:.2f}s', ha='center', va='bottom',
             fontsize=16, fontweight='bold', color='#1e293b')

# Delta annotation arrow
delta = ctrl_ro - combined_ro
ax2.annotate(f'$\\Delta = -{delta:.2f}s$',
             xy=(1, combined_ro), xytext=(0.5, 1.40),
             fontsize=13, fontweight='bold', color='#dc2626',
             arrowprops=dict(arrowstyle='->', color='#dc2626', lw=1.8),
             ha='center')

ax2.set_ylabel('Reaction Time (seconds)', fontsize=14, fontweight='bold')
ax2.set_title(f'Opponent Reaction Time: CRISC vs. Control\n'
              f'($T_O \\leq {T_O_THRESHOLD}s$, $N_{{CRISC}} = {combined_n:,}$, $N_{{Control}} = {ctrl_n_valid:,}$)',
              fontsize=13, fontweight='bold', pad=15)
ax2.set_ylim(0, 1.8)
ax2.tick_params(axis='both', labelsize=12)
ax2.grid(axis='y', alpha=0.3, zorder=1)
ax2.grid(axis='x', visible=False)

sns.despine(left=True, bottom=True)

fig2.savefig('./visuals/fig2_reaction.png')
plt.close(fig2)
print("Saved fig2_reaction.png")

print("\nAll visualizations generated successfully!")
