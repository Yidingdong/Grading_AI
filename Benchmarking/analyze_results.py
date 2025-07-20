import pandas as pd
import json
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import re
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches # <-- Added Import
import numpy as np

# --- CONFIGURATION ---
RESULTS_FILE = Path("./benchmark_grading_results_optimized.csv")
OUTPUT_DIR = Path("./analysis_charts_final")


# --- HELPER FUNCTIONS ---
def get_ai_points(value):
    if pd.isna(value) or not isinstance(value, str): return None
    json_match = re.search(r'\{.*\}', value, re.DOTALL)
    if not json_match: return None
    json_str = json_match.group(0)
    try:
        data = json.loads(json_str)
        points = data.get("awarded_points")
        if isinstance(points, (int, float)): return float(points)
        return None
    except (json.JSONDecodeError, TypeError):
        return None


# --- PLOTTING FUNCTIONS ---

def plot_winners_summary(winners):
    """Generates a clean, text-only table chart summarizing the winners."""
    print(" -> Generating Summary Chart...")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.axis('off')

    category_icons = {
        "Accuracy": "★",
        "Consistency": "⚖️",
        "Speed (Latency)": "⚡️",
        "Efficiency (Tokens)": "⚙️",
    }

    cell_text = []
    row_colours = [['white', 'white']] * len(winners)

    for category, winner in winners.items():
        icon = category_icons.get(category, '➡️')
        cell_text.append([f'{icon} {category}', winner])

    table = ax.table(
        cellText=cell_text,
        colLabels=['Category', 'Winner'],
        loc='center',
        cellLoc='left',
        colWidths=[0.4, 0.6],
        cellColours=row_colours
    )

    table.auto_set_font_size(False)
    table.set_fontsize(16)
    table.scale(1.2, 2.0)

    for (i, j), cell in table.get_celld().items():
        cell.set_edgecolor('black')
        cell.PAD = 0.05

        if i == 0:
            cell.set_text_props(weight='bold', color='white', ha='center')
            cell.set_facecolor('#4682B4')
        else:
            cell.set_text_props(ha='left')

    ax.set_title('Benchmark Winners Summary', fontsize=22, weight='bold', pad=20)
    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "summary.png", dpi=150)
    plt.close()

'''
def plot_accuracy_chart(stats_df, successful_df):
    """
    Generates a bar plot (for the mean percentage error) overlaid with a swarm plot
    (for individual data points) to show normalized accuracy and consistency.
    """
    print(" -> Generating 1. Accuracy & Consistency Chart (Normalized)...")
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))

    bar_width = 0.25 if len(stats_df.index) == 1 else 0.8

    sns.barplot(
        x=stats_df.index, y='mean_error', data=stats_df,
        palette='viridis_r', ax=ax, alpha=0.4, errorbar=None,
        width=bar_width,
        zorder=1
    )

    sns.swarmplot(
        x='model', y='grading_error_percent', data=successful_df,
        order=stats_df.index,
        color='darkviolet',
        edgecolor='black',
        linewidth=0.5,
        ax=ax,
        size=5,
        zorder=2
    )

    ax.set_title('AI Model Grading Accuracy & Consistency (Normalized)', fontsize=18, weight='bold')
    ax.set_xlabel('Model', fontsize=14)
    ax.set_ylabel('Grading Error (% of Max Points)', fontsize=14)

    plt.xticks(rotation=45, ha='right', fontsize=12)
    plt.yticks(fontsize=12)

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "1_accuracy_and_consistency.png", dpi=150)
    plt.close()


def plot_latency_chart(stats_df, raw_df):
    """
    Generates a bar plot (for the median) overlaid with a swarm plot
    (for individual data points) to show latency distribution.
    """
    print(" -> Generating 2. Latency (Speed) Chart...")
    latency_data = raw_df[raw_df['latency_seconds'] > 0]

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))

    bar_width = 0.25 if len(stats_df.index) == 1 else 0.8

    sns.barplot(
        x=stats_df.index, y='median_latency', data=stats_df,
        palette='coolwarm', ax=ax, alpha=0.4, errorbar=None,
        width=bar_width
    )

    sns.swarmplot(
        x='model', y='latency_seconds', data=latency_data,
        order=stats_df.index,
        color='navy', ax=ax, size=4
    )

    ax.set_title('Latency Distribution & Median (Speed)', fontsize=18, weight='bold')
    ax.set_xlabel('Model', fontsize=14)
    ax.set_ylabel('Response Time (seconds)', fontsize=14)

    plt.xticks(rotation=45, ha='right', fontsize=12)
    plt.yticks(fontsize=12)

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "2_latency_distribution.png", dpi=150)
    plt.close()


def plot_token_usage_chart(stats_df):
    """Generates a stacked bar chart for average token usage (vertical)."""
    print(" -> Generating 3. Token Usage (Efficiency) Chart...")
    token_data = stats_df.copy()
    token_data['total_avg_tokens'] = token_data['avg_input_tokens'] + token_data['avg_output_tokens']
    token_data = token_data.sort_values('total_avg_tokens', ascending=True)

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))

    # --- UPDATED --- Set bar width and ALSO axis limits for matplotlib
    bar_width = 0.25 if len(token_data.index) == 1 else 0.8

    ax.bar(token_data.index, token_data['avg_input_tokens'], width=bar_width, color='#3B82F6', label='Input Tokens')
    ax.bar(token_data.index, token_data['avg_output_tokens'], width=bar_width, bottom=token_data['avg_input_tokens'],
           color='#F97316',
           label='Output Tokens')

    if len(token_data.index) == 1:
        ax.set_xlim(-0.5, 0.5)  # Constrain axis to make the narrow bar look good

    ax.set_title('Average Token Usage per Model (Efficiency)', fontsize=18, weight='bold')
    ax.set_xlabel('Model', fontsize=14)
    ax.set_ylabel('Average Tokens per Request', fontsize=14)
    ax.legend(fontsize=10)

    plt.xticks(rotation=45, ha='right', fontsize=12)
    plt.yticks(fontsize=12)

    if not token_data.empty:
        max_tokens = token_data['total_avg_tokens'].max()
        ax.set_ylim(0, max_tokens * 1.2)

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "3_token_usage.png", dpi=150)
    plt.close()


def plot_performance_efficiency_chart(stats_df):
    """Generates a scatter plot comparing model accuracy and token efficiency."""
    print(" -> Generating 4. Performance vs. Efficiency Chart...")
    plot_data = stats_df[stats_df['successful_grades'] > 0].copy()

    if plot_data.empty: return

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))

    sns.scatterplot(
        data=plot_data,
        x='mean_error',
        y='total_avg_tokens',
        hue=plot_data.index,
        s=400,
        palette='viridis',
        legend=False,
        ax=ax
    )

    for i, row in plot_data.iterrows():
        ax.text(row['mean_error'], row['total_avg_tokens'] * 1.01, i, fontsize=11, ha='center', va='bottom',
                bbox=dict(boxstyle="round,pad=0.2", fc="yellow", ec="black", lw=0.5, alpha=0.7))

    ax.set_title('Performance vs. Efficiency Analysis', fontsize=18, weight='bold')
    ax.set_xlabel('Average Percentage Deviation (Lower is Better)', fontsize=14)
    ax.set_ylabel('Average Total Tokens per Request (Lower is Better)', fontsize=14)

    if len(plot_data) == 1:
        x_val = plot_data['mean_error'].iloc[0]
        y_val = plot_data['total_avg_tokens'].iloc[0]
        ax.set_xlim(x_val * 0.9, x_val * 1.1)
        ax.set_ylim(y_val * 0.9, y_val * 1.1)

    ax.grid(True)
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "4_performance_vs_efficiency.png", dpi=150)
    plt.close()
'''


def plot_consistency_distribution(df, model_order):
    print(" -> Generating 7. Consistency Distribution Chart (Violin Plot)...")
    successful_df = df[df['ai_awarded_points'].notna()].copy()

    if successful_df.empty or successful_df['max_points'].sum() == 0:
        print("    -> Skipping chart: No successful data to plot consistency.")
        return

    successful_df = successful_df[successful_df['max_points'] > 0]
    successful_df['actual_percent'] = (successful_df['actual_points'] / successful_df['max_points']) * 100
    successful_df['ai_percent'] = (successful_df['ai_awarded_points'] / successful_df['max_points']) * 100
    successful_df['percent_point_bias'] = successful_df['ai_percent'] - successful_df['actual_percent']

    consistency_scores = successful_df.groupby('subject')['percent_point_bias'].std()
    subject_order = consistency_scores.sort_values(ascending=False).index

    norm = mcolors.Normalize(vmin=consistency_scores.min(), vmax=consistency_scores.max())
    cmap = cm.get_cmap('coolwarm')
    color_palette = {subject: cmap(norm(consistency_scores[subject])) for subject in subject_order}

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 8))

    sns.violinplot(
        data=successful_df,
        x='percent_point_bias',
        y='subject',
        order=subject_order,
        palette=color_palette,
        inner=None,
        orient='h',
        ax=ax
    )

    for i, subject in enumerate(subject_order):
        median_val = successful_df[successful_df['subject'] == subject]['percent_point_bias'].median()
        ax.plot([median_val, median_val], [i - 0.15, i + 0.15],
                color='dimgray',
                solid_capstyle='round',
                lw=3.5,
                zorder=3)

    ax.axvline(0, color='darkgrey', linewidth=1, linestyle='--', zorder=0)

    ax.set_title('Consistency Analysis: Distribution of Grading Deviation by Subject', fontsize=18, weight='bold')
    ax.set_xlabel('Percentage Point Difference (AI % - Teacher %)', fontsize=14)
    ax.set_ylabel('Subject', fontsize=14)

    plt.text(0.98, 0.02, '← Harsher Grader | Easier Grader →',
             va='bottom', ha='right', transform=plt.gca().transAxes, color='gray', fontsize=10)

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "7_consistency_distribution_color_coded.png", dpi=150)
    plt.close()

def plot_normalized_bias_heatmap(df):
    print(" -> Generating 5. Subject Bias Heatmap (Normalized)...")
    successful_df = df[df['ai_awarded_points'].notna()].copy()

    successful_df = successful_df[successful_df['max_points'] > 0]

    successful_df['actual_percent'] = (successful_df['actual_points'] / successful_df['max_points']) * 100
    successful_df['ai_percent'] = (successful_df['ai_awarded_points'] / successful_df['max_points']) * 100

    successful_df['percent_deviation'] = (successful_df['ai_percent'] - successful_df['actual_percent']).abs()

    bias_data = successful_df.groupby(['model', 'subject'])['percent_deviation'].mean().unstack()

    if bias_data.empty or bias_data.shape[1] < 2:
        print("    -> Skipping chart: Not enough subject diversity to generate bias heatmap.")
        return

    plt.style.use('seaborn-v0_8-whitegrid')
    fig_height = max(5, bias_data.shape[0] * 0.8)
    fig_width = max(8, bias_data.shape[1] * 2)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    sns.heatmap(bias_data, annot=True, fmt=".2f", cmap="Reds", linewidths=.5, ax=ax, annot_kws={"fontsize": 11})

    ax.set_title('Normalized Bias Check: Average Percentage Point Deviation by Subject', fontsize=18, weight='bold')
    ax.set_xlabel('Subject', fontsize=14)
    ax.set_ylabel('Model', fontsize=14)

    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "5_subject_bias_heatmap_normalized.png", dpi=150)
    plt.close()


def plot_grading_tendency_chart(df, model_order):
    print(" -> Generating 6. Grading Tendency Chart (Normalized with Data Types)...")
    successful_df = df[df['ai_awarded_points'].notna()].copy()

    if successful_df.empty or successful_df['max_points'].sum() == 0:
        print("    -> Skipping chart: No successful data to plot tendency.")
        return

    successful_df = successful_df[successful_df['max_points'] > 0]
    successful_df['actual_percent'] = (successful_df['actual_points'] / successful_df['max_points']) * 100
    successful_df['ai_percent'] = (successful_df['ai_awarded_points'] / successful_df['max_points']) * 100
    successful_df['percent_point_bias'] = successful_df['ai_percent'] - successful_df['actual_percent']

    plot_data = successful_df.groupby(['subject', 'data_type'])['percent_point_bias'].mean().reset_index()
    plot_data = plot_data.sort_values('subject', ascending=True) # Sort for consistent plotting order

    if plot_data.empty:
        print("    -> Skipping chart: No successful data to plot bias.")
        return

    color_map = {
        "Klausuren": "#B22222",  # Firebrick red for real data
        "KI_Daten": "#4682B4"   # Steelblue for AI data
    }
    bar_colors = plot_data['data_type'].map(color_map).tolist()

    # 3. Use a standard Matplotlib horizontal bar plot.
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 8)) # Use the original figsize

    ax.barh(
        y=plot_data['subject'],
        width=plot_data['percent_point_bias'],
        color=bar_colors,
        height=0.8
    )

    legend_patches = [mpatches.Patch(color=color, label=label) for label, color in color_map.items()]
    ax.legend(handles=legend_patches, title='Data Type')

    ax.set_title('Normalized AI Grading Tendency vs. Human Teacher', fontsize=18, weight='bold')
    ax.set_xlabel('Average Percentage Point Difference (AI % - Teacher %)', fontsize=14)
    ax.set_ylabel('Subject', fontsize=14)
    ax.axvline(0, color='black', linewidth=0.8, linestyle='--')
    ax.grid(axis='x', linestyle='--', alpha=0.7)

    plt.text(0.98, 0.02, '← Harsher Grader | Easier Grader →',
             va='bottom', ha='right', transform=plt.gca().transAxes, color='gray', fontsize=10)

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "6_grading_tendency_normalized_by_type.png", dpi=150)
    plt.close()

# --- MAIN ANALYSIS SCRIPT ---
def analyze_full_report(filepath):
    if not filepath.exists():
        print(f"Error: Results file not found at '{filepath}'");
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Loading results from '{filepath}'...")
    df = pd.read_csv(filepath)

    df['ai_awarded_points'] = df['ai_evaluation_json'].apply(get_ai_points)
    df_successful = df[df['ai_awarded_points'].notna()].copy()

    if df_successful.empty:
        print("\nNo successful grading results found. Cannot generate analysis.");
        return

    df_successful['grading_error'] = (df_successful['ai_awarded_points'] - df_successful['actual_points']).abs()

    df_successful = df_successful[df_successful['max_points'] > 0].copy()
    df_successful['grading_error_percent'] = (df_successful['grading_error'] / df_successful['max_points']) * 100

    accuracy_stats = df_successful.groupby('model')['grading_error_percent'].agg(
        mean_error='mean',
        std_dev_error='std'
    )

    total_attempts = df.groupby('model')['job_id'].count().rename('total_attempts')
    successful_grades = df_successful.groupby('model')['job_id'].count().rename('successful_grades')
    token_stats = df.groupby('model')[['input_tokens', 'output_tokens']].mean().rename(columns={
        'input_tokens': 'avg_input_tokens', 'output_tokens': 'avg_output_tokens'
    })
    latency_stats = df[df['latency_seconds'] > 0].groupby('model')['latency_seconds'].median().rename('median_latency')

    final_stats = pd.concat([total_attempts, successful_grades, accuracy_stats, token_stats, latency_stats], axis=1)

    final_stats['successful_grades'] = final_stats['successful_grades'].fillna(0).astype(int)
    final_stats['success_rate_%'] = (final_stats['successful_grades'] / final_stats['total_attempts'] * 100).round(1)
    final_stats['total_avg_tokens'] = final_stats['avg_input_tokens'] + final_stats['avg_output_tokens']

    final_stats_sorted = final_stats.sort_values(by=['success_rate_%', 'mean_error'], ascending=[False, True])

    print("\n--- Full Model Statistics Summary ---");
    print(final_stats_sorted.to_string(formatters={'mean_error': '{:.2f}%'.format, 'std_dev_error': '{:.2f}%'.format}))

    prompt_total = df.groupby('prompt_style')['job_id'].count().rename('total_attempts')
    prompt_success = df_successful.groupby('prompt_style')['job_id'].count().rename('successful_grades')
    prompt_accuracy = df_successful.groupby('prompt_style')['grading_error_percent'].agg(
        mean_error='mean', std_dev_error='std'
    )
    prompt_latency = df[df['latency_seconds'] > 0].groupby('prompt_style')['latency_seconds'].median().rename(
        'median_latency')

    prompt_stats = pd.concat([prompt_total, prompt_success, prompt_accuracy, prompt_latency], axis=1)
    prompt_stats['successful_grades'] = prompt_stats['successful_grades'].fillna(0).astype(int)
    prompt_stats['success_rate_%'] = (prompt_stats['successful_grades'] / prompt_stats['total_attempts'] * 100).round(1)
    prompt_stats_sorted = prompt_stats.sort_values(by=['success_rate_%', 'mean_error'], ascending=[False, True])

    print("\n--- Prompt Style Performance Summary ---")
    print(prompt_stats_sorted.to_string(formatters={'mean_error': '{:.2f}%'.format, 'std_dev_error': '{:.2f}%'.format}))

    # --- Winner Calculation ---
    successful_models = final_stats_sorted[final_stats_sorted['successful_grades'] > 0].copy()
    if not successful_models.empty:
        winners = {
            "Accuracy": successful_models['mean_error'].idxmin(),
            "Consistency": successful_models['std_dev_error'].idxmin(),
            "Speed (Latency)": successful_models['median_latency'].idxmin(),
            "Efficiency (Tokens)": successful_models['total_avg_tokens'].idxmin(),
        }
    else:
        winners = {"Error": "No successful models found"}

    print("\n--- Generating Measurable Analysis Charts ---")
    #plot_winners_summary(winners)
    #plot_accuracy_chart(final_stats_sorted, df_successful)
    #plot_latency_chart(final_stats_sorted, df)
    #plot_token_usage_chart(final_stats_sorted)
    #plot_performance_efficiency_chart(final_stats_sorted)
    plot_normalized_bias_heatmap(df)
    plot_grading_tendency_chart(df, model_order=final_stats_sorted.index)
    plot_consistency_distribution(df, model_order=final_stats_sorted.index)

    print(f"\nAnalysis complete. All charts saved to the '{OUTPUT_DIR}' directory.")


if __name__ == "__main__":
    analyze_full_report(RESULTS_FILE)