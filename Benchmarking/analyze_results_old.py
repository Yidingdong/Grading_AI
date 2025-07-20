import pandas as pd
import json
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import seaborn as sns
from pathlib import Path
import re

# --- CONFIGURATION ---
RESULTS_FILE = Path("./benchmark_grading_results_old.csv")
OUTPUT_DIR = Path("./analysis_charts_old")


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

def plot_latency_chart(df, model_order):
    """Generates and saves the latency distribution as a Violin Plot (vertical)."""
    print(" -> Generating 1. Latency (Speed) Chart...")
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

    if not latency_data.empty:
        max_latency = latency_data['latency_seconds'].max()
        ax.set_ylim(0, max_latency * 1.2)

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "1_latency_distribution.png", dpi=150)
    plt.close()


def plot_token_usage_chart(stats_df):
    """Generates a stacked bar chart for average token usage (vertical)."""
    print(" -> Generating 2. Token Usage (Efficiency) Chart...")
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

    if not token_data.empty:
        max_tokens = token_data['total_avg_tokens'].max()
        ax.set_ylim(0, max_tokens * 1.2)

    plt.tight_layout(pad=1.5)
    plt.savefig(OUTPUT_DIR / "2_token_usage.png", dpi=150)
    plt.close()


def plot_grading_tendency_chart(df):
    """
    Generates a diverging bar chart with labels placed on the opposite side
    of the zero-line from their corresponding bar.
    """
    print(" -> Generating 3. Grading Tendency Chart (Normalized)...")
    successful_df = df[df['ai_awarded_points'].notna()].copy()
    successful_df = successful_df[successful_df['max_points'] > 0]

    if successful_df.empty:
        print("    -> Skipping chart: No successful data to plot bias.")
        return

    successful_df['actual_percent'] = (successful_df['actual_points'] / successful_df['max_points']) * 100
    successful_df['ai_percent'] = (successful_df['ai_awarded_points'] / successful_df['max_points']) * 100
    successful_df['percent_point_bias'] = successful_df['ai_percent'] - successful_df['actual_percent']

    bias_by_subject = successful_df.groupby(['subject', 'model'])['percent_point_bias'].mean().unstack()

    if bias_by_subject.empty:
        print("    -> Skipping chart: No successful data to plot bias.")
        return

    # --- Sort and Color logic ---
    model_abs_bias = bias_by_subject.abs().mean()
    sorted_models = model_abs_bias.sort_values().index.tolist()

    cmap = cm.get_cmap('coolwarm')
    norm = mcolors.Normalize(vmin=model_abs_bias.min(), vmax=model_abs_bias.max())
    model_colors = {model: cmap(norm(bias)) for model, bias in model_abs_bias.items()}
    plot_colors = [model_colors[m] for m in sorted_models]
    # --- End Sort and Color logic ---

    ax = bias_by_subject[sorted_models].plot(
        kind='barh',
        figsize=(12, max(6, len(bias_by_subject) * 1.5)),
        width=0.8,
        color=plot_colors,
        legend=False
    )

    ax.set_title('Normalized AI Grading Tendency vs. Human Teacher', fontsize=18, weight='bold')
    ax.set_xlabel('Average Percentage Point Difference (AI % - Teacher %)', fontsize=14)
    ax.set_ylabel('Subject', fontsize=14)
    ax.axvline(0, color='black', linewidth=0.8, linestyle='--')
    ax.grid(axis='x', linestyle='--', alpha=0.7)

    # --- UPDATED: Label bars individually on the 'empty' side of the zero line ---
    # Define a small padding from the zero line for the text
    padding = (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.01

    # Add the text labels
    for i, bar in enumerate(ax.patches):
        model_name = sorted_models[i]
        value = bar.get_width()

        # If bar extends left (negative), place label on the right of zero, left-aligned.
        if value < 0:
            ha = 'left'
            x_pos = padding
        # If bar extends right (positive), place label on the left of zero, right-aligned.
        else:
            ha = 'right'
            x_pos = -padding

        ax.text(x_pos, bar.get_y() + bar.get_height() / 2, model_name, va='center', ha=ha, fontsize=10)
    # --- END UPDATED ---

    ax.text(0.98, 0.02, '← Harsher Grader | Easier Grader →',
             va='bottom', ha='right', transform=ax.transAxes, color='gray', fontsize=10)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "3_grading_tendency_normalized.png", dpi=150)
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

    # --- This block is kept for sorting and providing context ---
    accuracy_stats = df_successful.groupby('model')['grading_error'].agg(mean_error='mean')
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
    # --- End of context block ---

    print("\n--- Full Model Statistics Summary ---");
    print(final_stats_sorted.to_string())

    print("\n--- Generating Requested Analysis Charts ---")
    plot_latency_chart(df, model_order=final_stats_sorted.index)
    plot_token_usage_chart(final_stats_sorted)
    plot_grading_tendency_chart(df)

    print(f"\nAnalysis complete. The 3 requested charts have been saved to the '{OUTPUT_DIR}' directory.")


if __name__ == "__main__":
    analyze_full_report(RESULTS_FILE)