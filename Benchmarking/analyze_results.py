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

    # Prepare data and colors for the table (no emojis)
    for category, winner in winners.items():
        cell_text.append([category, winner])
        if category == "Overall Best":
            row_colours.append(['#FFFACD', '#FFFACD'])  # Lemon Chiffon for the highlight
        else:
            row_colours.append(['white', 'white'])

    table = ax.table(
        cellText=cell_text,
        colLabels=['Category', 'Winner'],
        loc='center',
        cellLoc='left',  # Align text to the left for readability
        colWidths=[0.4, 0.6],
        cellColours=row_colours
    )

    table.auto_set_font_size(False)
    table.set_fontsize(16)
    table.scale(1.2, 2.0)

    # Style table cells for a professional look
    for (i, j), cell in table.get_celld().items():
        cell.set_edgecolor('black')
        cell.PAD = 0.05  # Add some padding to the left of the text

        # Header styling
        if i == 0:
            cell.set_text_props(weight='bold', color='white', ha='center')
            cell.set_facecolor('#4682B4')
        # Overall winner row styling
        elif i == len(winners):
            cell.set_text_props(weight='bold', ha='left')
        # Other content cells
        else:
            cell.set_text_props(ha='left')

    ax.set_title('Benchmark Winners Summary', fontsize=22, weight='bold', pad=20)
    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "0_winners_summary.png", dpi=150)
    plt.close()


def plot_accuracy_chart(stats_df):
    """Generates and saves the accuracy chart with error bars for consistency."""
    print(" -> Generating 1. Accuracy & Consistency Chart...")
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, len(stats_df) * 0.8 + 1))

    sns.barplot(x='mean_error', y=stats_df.index, data=stats_df, palette='viridis_r', orient='h', ax=ax)
    ax.errorbar(x=stats_df['mean_error'], y=stats_df.index, xerr=stats_df['std_dev_error'], fmt='none', ecolor='black',
                capsize=4)

    ax.set_title('AI Model Grading Accuracy & Consistency', fontsize=16, weight='bold')
    ax.set_xlabel('Average Point Deviation (Error Bars = Standard Deviation)')
    ax.set_ylabel('Model')
    ax.invert_yaxis()

    for index, (model_name, row) in enumerate(stats_df.iterrows()):
        if row['successful_grades'] > 0:
            ax.text(row.mean_error, index, f" {row.mean_error:.2f}", va='center', ha='left')
        else:
            ax.text(0.01, index, f" 100% FAILURE (0/{int(row.total_attempts)})", va='center', ha='left', color='red',
                    fontweight='bold')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "1_accuracy_and_consistency.png")
    plt.close()


def plot_latency_chart(df, model_order):
    """Generates and saves the latency distribution as a Violin Plot."""
    print(" -> Generating 2. Latency (Speed) Chart...")
    latency_data = df[df['latency_seconds'] > 0]

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, len(model_order) * 0.8 + 1))

    sns.violinplot(x='latency_seconds', y='model', data=latency_data, palette='coolwarm', orient='h', order=model_order,
                   ax=ax, inner='quartile')

    ax.set_title('Latency Distribution per Model (Speed)', fontsize=16, weight='bold')
    ax.set_xlabel('Response Time (seconds) - Lower is Better')
    ax.set_ylabel('Model')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "2_latency_distribution.png")
    plt.close()


def plot_token_usage_chart(stats_df):
    """Generates a stacked bar chart for average token usage."""
    print(" -> Generating 3. Token Usage (Efficiency) Chart...")
    token_data = stats_df.copy()
    token_data['total_avg_tokens'] = token_data['avg_input_tokens'] + token_data['avg_output_tokens']
    token_data = token_data.sort_values('total_avg_tokens', ascending=True)

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, len(token_data) * 0.8 + 1))

    ax.barh(token_data.index, token_data['avg_input_tokens'], color='#3B82F6', label='Input Tokens')
    ax.barh(token_data.index, token_data['avg_output_tokens'], left=token_data['avg_input_tokens'], color='#F97316',
            label='Output Tokens')

    ax.set_title('Average Token Usage per Model (Efficiency)', fontsize=16, weight='bold')
    ax.set_xlabel('Average Tokens per Request')
    ax.set_ylabel('Model')
    ax.legend()

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "3_token_usage.png")
    plt.close()


def plot_performance_efficiency_chart(stats_df):
    """Generates a scatter plot comparing model accuracy and token efficiency."""
    print(" -> Generating 4. Performance vs. Efficiency Chart...")
    plot_data = stats_df[stats_df['successful_grades'] > 0].copy()

    if plot_data.empty: return

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 8))

    sns.scatterplot(data=plot_data, x='total_avg_tokens', y='mean_error', hue=plot_data.index, s=200, palette='viridis',
                    legend=False, ax=ax)

    for i, row in plot_data.iterrows():
        ax.text(row['total_avg_tokens'] * 1.02, row['mean_error'], i, fontsize=9)

    ax.set_title('Performance vs. Efficiency Analysis', fontsize=16, weight='bold')
    ax.set_xlabel('Average Total Tokens per Request - Lower is Better (More Efficient) →')
    ax.set_ylabel('Average Point Deviation - Lower is Better (More Accurate) →')

    ax.annotate(
        'Ideal models are here\n(High Accuracy, High Efficiency)',
        xy=(plot_data['total_avg_tokens'].min(), plot_data['mean_error'].min()),
        xytext=(plot_data['total_avg_tokens'].quantile(0.6), plot_data['mean_error'].quantile(0.6)),
        arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=8),
        fontsize=12,
        bbox=dict(boxstyle="round,pad=0.3", fc="yellow", ec="black", lw=1, alpha=0.5)
    )
    ax.grid(True)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "4_performance_vs_efficiency.png")
    plt.close()


def plot_bias_heatmap(df):
    """Generates a heatmap to check for performance bias across subjects."""
    print(" -> Generating 5. Subject Bias Heatmap...")
    successful_df = df[df['ai_awarded_points'].notna()].copy()
    successful_df['grading_error'] = (successful_df['ai_awarded_points'] - successful_df['actual_points']).abs()

    bias_data = successful_df.groupby(['model', 'subject'])['grading_error'].mean().unstack()

    if bias_data.empty or bias_data.shape[1] < 2:
        print("    -> Skipping chart: Not enough subject diversity to generate bias heatmap.")
        return

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))

    sns.heatmap(bias_data, annot=True, fmt=".2f", cmap="Reds", linewidths=.5, ax=ax)

    ax.set_title('Bias Check: Average Grading Error by Subject', fontsize=16, weight='bold')
    ax.set_xlabel('Subject')
    ax.set_ylabel('Model')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "5_subject_bias_heatmap.png")
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

    final_stats_sorted = final_stats.sort_values(by=['success_rate_%', 'mean_error'], ascending=[False, True])

    print("\n--- Full Model Statistics Summary ---")
    print(final_stats_sorted.to_string())

    # --- Determine Winners ---
    successful_models = final_stats_sorted[final_stats_sorted['successful_grades'] > 0]

    if not successful_models.empty:
        # Create a copy to avoid SettingWithCopyWarning
        successful_models = successful_models.copy()
        successful_models['accuracy_rank'] = successful_models['mean_error'].rank()
        successful_models['consistency_rank'] = successful_models['std_dev_error'].rank()
        successful_models['efficiency_rank'] = successful_models['total_avg_tokens'].rank()
        successful_models['overall_score'] = successful_models['accuracy_rank'] + successful_models[
            'consistency_rank'] + successful_models['efficiency_rank']

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