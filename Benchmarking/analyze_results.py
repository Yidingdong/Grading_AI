import pandas as pd
import json
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import re

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
    print(" -> Generating 0. Winners Summary Chart...")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axis('off')

    cell_text = []
    row_colours = []

    for category, winner in winners.items():
        cell_text.append([category, winner])
        if category == "Overall Best":
            row_colours.append(['#FFFACD', '#FFFACD'])
        else:
            row_colours.append(['white', 'white'])

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
        elif i == len(winners):
            cell.set_text_props(weight='bold', ha='left')
        else:
            cell.set_text_props(ha='left')

    ax.set_title('Benchmark Winners Summary', fontsize=22, weight='bold', pad=20)
    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "0_winners_summary.png", dpi=150)
    plt.close()


def plot_accuracy_chart(stats_df):
    """Generates and saves the accuracy chart with error bars for consistency (vertical)."""
    print(" -> Generating 1. Accuracy & Consistency Chart...")
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))

    sns.barplot(
        x=stats_df.index,
        y='mean_error',
        data=stats_df,
        palette='viridis_r',
        ax=ax
    )

    ax.errorbar(
        x=stats_df.index,
        y=stats_df['mean_error'],
        yerr=stats_df['std_dev_error'],
        fmt='none',
        ecolor='black',
        capsize=8,  # Increased capsize
        elinewidth=2  # Increased line width
    )

    ax.set_title('AI Model Grading Accuracy & Consistency', fontsize=18, weight='bold')
    ax.set_xlabel('Model', fontsize=14)
    ax.set_ylabel('Average Point Deviation (Error Bars = Standard Deviation)', fontsize=14)

    plt.xticks(rotation=45, ha='right', fontsize=12)
    plt.yticks(fontsize=12)

    # --- MODIFICATION: Adjusted Y-axis limit for better visibility with limited data ---
    max_error = stats_df['mean_error'].max() + stats_df['std_dev_error'].max() * 1.5
    ax.set_ylim(0, max(1.0, max_error))  # Ensure y-axis starts at 0 and has enough space above

    for i, (model_name, row) in enumerate(stats_df.iterrows()):
        if row['successful_grades'] > 0:
            # Position text carefully based on the mean and std dev
            text_y_pos = row['mean_error'] + row['std_dev_error'] + (
                        ax.get_ylim()[1] * 0.02)  # Adjusted based on plot height
            ax.text(
                i,
                text_y_pos,
                f"{row['mean_error']:.2f}",
                va='bottom',
                ha='center',
                fontsize=11,  # Increased font size
                color='black',  # Ensure text color is visible
                fontweight='bold'
            )
            ax.text(
                i,
                text_y_pos + (ax.get_ylim()[1] * 0.02),  # Slightly above the mean text
                f"(Success: {row['success_rate_%']}%)",
                va='bottom',
                ha='center',
                fontsize=9,
                color='gray'
            )
        else:
            ax.text(
                i,
                ax.get_ylim()[1] * 0.5,  # Place failure text in the middle of the plot area
                f"100% FAILURE\n(0/{int(row.total_attempts)})",
                va='center',
                ha='center',
                color='red',
                fontweight='bold',
                fontsize=12  # Increased font size
            )

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "1_accuracy_and_consistency.png", dpi=150)
    plt.close()


def plot_latency_chart(df, model_order):
    """Generates and saves the latency distribution as a Violin Plot (vertical)."""
    print(" -> Generating 2. Latency (Speed) Chart...")
    latency_data = df[df['latency_seconds'] > 0]

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))

    sns.violinplot(
        x='model',
        y='latency_seconds',
        data=latency_data,
        palette='coolwarm',
        order=model_order,
        ax=ax,
        inner='quartile'
    )

    ax.set_title('Latency Distribution per Model (Speed)', fontsize=18, weight='bold')
    ax.set_xlabel('Model', fontsize=14)
    ax.set_ylabel('Response Time (seconds) - Lower is Better', fontsize=14)

    plt.xticks(rotation=45, ha='right', fontsize=12)
    plt.yticks(fontsize=12)

    # --- MODIFICATION: Adjust Y-axis limit for latency if data is sparse ---
    if not latency_data.empty:
        max_latency = latency_data['latency_seconds'].max()
        ax.set_ylim(0, max_latency * 1.2)  # Give 20% extra space above max latency

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

    ax.bar(token_data.index, token_data['avg_input_tokens'], color='#3B82F6', label='Input Tokens')
    ax.bar(token_data.index, token_data['avg_output_tokens'], bottom=token_data['avg_input_tokens'], color='#F97316',
           label='Output Tokens')

    ax.set_title('Average Token Usage per Model (Efficiency)', fontsize=18, weight='bold')
    ax.set_xlabel('Model', fontsize=14)
    ax.set_ylabel('Average Tokens per Request', fontsize=14)
    ax.legend(fontsize=10)

    plt.xticks(rotation=45, ha='right', fontsize=12)
    plt.yticks(fontsize=12)

    # --- MODIFICATION: Adjust Y-axis limit for token usage if data is sparse ---
    if not token_data.empty:
        max_tokens = token_data['total_avg_tokens'].max()
        ax.set_ylim(0, max_tokens * 1.2)  # Give 20% extra space above max tokens

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "3_token_usage.png", dpi=150)
    plt.close()


def plot_performance_efficiency_chart(stats_df):
    """Generates a scatter plot comparing model accuracy and token efficiency (swapped axes)."""
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
        s=400,  # Increased size of points for better visibility
        palette='viridis',
        legend=False,
        ax=ax
    )

    # --- MODIFICATION: Remove arrow annotation ---
    # ax.annotate(...) # Removed this block

    # --- MODIFICATION: Adjust axis limits to fit sparse data if only one point ---
    if len(plot_data) == 1:
        x_val = plot_data['mean_error'].iloc[0]
        y_val = plot_data['total_avg_tokens'].iloc[0]
        ax.set_xlim(x_val * 0.9, x_val * 1.1)  # 10% padding around single point
        ax.set_ylim(y_val * 0.9, y_val * 1.1)  # 10% padding around single point
    else:
        # For multiple points, set limits based on data range
        ax.set_xlim(plot_data['mean_error'].min() * 0.9, plot_data['mean_error'].max() * 1.1)
        ax.set_ylim(plot_data['total_avg_tokens'].min() * 0.9, plot_data['total_avg_tokens'].max() * 1.1)

    for i, row in plot_data.iterrows():
        ax.text(row['mean_error'], row['total_avg_tokens'] * 1.01, i, fontsize=11, ha='center', va='bottom',
                bbox=dict(boxstyle="round,pad=0.2", fc="yellow", ec="black", lw=0.5,
                          alpha=0.7))  # Added bbox for clarity

    ax.set_title('Performance vs. Efficiency Analysis', fontsize=18, weight='bold')
    ax.set_xlabel('Average Point Deviation (More Accurate →)', fontsize=14)
    ax.set_ylabel('Average Total Tokens per Request (More Efficient →)', fontsize=14)

    ax.grid(True)
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "4_performance_vs_efficiency.png", dpi=150)
    plt.close()


def plot_bias_heatmap(df):
    """Generates a heatmap to check for performance bias across subjects."""
    print(" -> Generating 5. Subject Bias Heatmap...")
    successful_df = df[df['ai_awarded_points'].notna()].copy()
    successful_df['grading_error'] = (successful_df['ai_awarded_points'] - successful_df['actual_points']).abs()

    bias_data = successful_df.groupby(['model', 'subject'])['grading_error'].mean().unstack(fill_value=None)

    if bias_data.empty or bias_data.shape[1] < 2:
        print(
            "    -> Skipping chart: Not enough subject diversity to generate bias heatmap (need at least 2 subjects with data).")
        return

    plt.style.use('seaborn-v0_8-whitegrid')
    # Dynamically adjust figsize based on number of models and subjects
    fig_height = max(5, bias_data.shape[0] * 0.8)
    fig_width = max(8, bias_data.shape[1] * 2)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    sns.heatmap(bias_data, annot=True, fmt=".2f", cmap="Reds", linewidths=.5, ax=ax, annot_kws={"fontsize": 11})

    ax.set_title('Bias Check: Average Grading Error by Subject', fontsize=18, weight='bold')
    ax.set_xlabel('Subject', fontsize=14)
    ax.set_ylabel('Model', fontsize=14)

    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "5_subject_bias_heatmap.png", dpi=150)
    plt.close()


# --- MAIN ANALYSIS SCRIPT ---
def analyze_full_report(filepath):
    if not filepath.exists():
        print(f"Error: Results file not found at '{filepath}'")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Loading results from '{filepath}'...")
    df = pd.read_csv(filepath)

    df['ai_awarded_points'] = df['ai_evaluation_json'].apply(get_ai_points)
    df_successful = df[df['ai_awarded_points'].notna()].copy()

    if df_successful.empty:
        print("\nNo successful grading results found. Cannot generate analysis.")
        return

    df_successful['grading_error'] = (df_successful['ai_awarded_points'] - df_successful['actual_points']).abs()

    accuracy_stats = df_successful.groupby('model')['grading_error'].agg(mean_error='mean', std_dev_error='std')
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

    # Sort by success rate, then mean error. This order is important for consistency across charts.
    final_stats_sorted = final_stats.sort_values(by=['success_rate_%', 'mean_error'], ascending=[False, True])

    print("\n--- Full Model Statistics Summary ---")
    print(final_stats_sorted.to_string())

    # --- Determine Winners ---
    successful_models = final_stats_sorted[final_stats_sorted['successful_grades'] > 0].copy()

    if not successful_models.empty:
        successful_models['accuracy_rank'] = successful_models['mean_error'].rank()
        successful_models['consistency_rank'] = successful_models['std_dev_error'].rank()
        successful_models['efficiency_rank'] = successful_models['total_avg_tokens'].rank()
        successful_models['speed_rank'] = successful_models['median_latency'].rank()

        successful_models['overall_score'] = successful_models['accuracy_rank'] + \
                                             successful_models['consistency_rank'] + \
                                             successful_models['efficiency_rank'] + \
                                             successful_models['speed_rank']

        winners = {
            "Accuracy": successful_models['mean_error'].idxmin(),
            "Consistency": successful_models['std_dev_error'].idxmin(),
            "Speed (Latency)": successful_models['median_latency'].idxmin(),
            "Efficiency (Tokens)": successful_models['total_avg_tokens'].idxmin(),
            "Overall Best": successful_models['overall_score'].idxmin()
        }
    else:
        winners = {"Error": "No successful models found"}

    # --- Generate All Charts ---
    print("\n--- Generating Measurable Analysis Charts ---")
    plot_winners_summary(winners)
    plot_accuracy_chart(final_stats_sorted)
    plot_latency_chart(df, model_order=final_stats_sorted.index)
    plot_token_usage_chart(final_stats_sorted)
    plot_performance_efficiency_chart(final_stats_sorted)
    plot_bias_heatmap(df)

    print(f"\nAnalysis complete. All charts saved to the '{OUTPUT_DIR}' directory.")


if __name__ == "__main__":
    analyze_full_report(RESULTS_FILE)