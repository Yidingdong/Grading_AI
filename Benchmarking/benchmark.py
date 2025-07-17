import asyncio
import time
import pandas as pd
from openai import AsyncOpenAI, APIError
from pathlib import Path
import re
import random

# --- 1. CONFIGURATION ---
MODELS_TO_TEST = [
    "gpt-4o-mini",
    # "gemma3-27b",
    # "qwen3-235b",
    # "qwen3-30b",
    # "qwen3-235b-reasoning",
    # "qwen3-30b-reasoning",
    # "gpt-4o",
]
DATA_ROOT_PATH = Path("./DataCollection")
PROMPTS_PATH = Path("./prompts")
RESULTS_FILEPATH = Path("./benchmark_grading_results_optimized.csv")
BASE_URL = "https://api.seedbox.ai/v1"

# Per-model concurrency limits
MODEL_CONFIG = {
    "gpt-4o-mini": 50,
    "gpt-4o": 10,
    "qwen3-30b": 20,
    "qwen3-235b": 5,
    "qwen3-30b-reasoning": 15,
    "qwen3-235b-reasoning": 4,
    "gemma3-27b": 15,
}
DEFAULT_CONCURRENCY_LIMIT = 10
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0


# --- 2. ASYNCHRONOUS WORKER ---
async def grade_task_worker(semaphore_map, client, job, prompt_name, template, model_name):
    """Performs a single grading API call."""
    semaphore = semaphore_map[model_name]
    async with semaphore:
        level = "Leistungskurs" if job['subject'] in ["Chemie", "Wirtschaft"] else "Basiskurs"

        user_prompt = template['user'].format(
            subject=job['subject'], level=level, max_points=job['max_points'],
            task_text=job['task_text'], student_answer=job['student_answer'],
            materials_text=job.get('materials_text', "Keine Materialien vorhanden.")
        )
        messages = [{"role": "system", "content": template['system']}, {"role": "user", "content": user_prompt}]
        job_id = job['job_id']
        print(f"Starting job: {job_id} | Model: {model_name}")

        retry_delay = INITIAL_RETRY_DELAY
        for attempt in range(MAX_RETRIES):
            try:
                start_time = time.monotonic()
                completion = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1
                )
                end_time = time.monotonic()

                input_tokens = completion.usage.prompt_tokens
                output_tokens = completion.usage.completion_tokens

                print(f"  -> SUCCESS on job: {job_id} | Model: {model_name} in {end_time - start_time:.2f}s")
                return {
                    "job_id": job_id, "subject": job['subject'], "model": model_name, "prompt_style": prompt_name,
                    "max_points": job['max_points'], "actual_points": job['actual_points'],
                    "ai_evaluation_json": completion.choices[0].message.content,
                    "latency_seconds": end_time - start_time,
                    "input_tokens": input_tokens, "output_tokens": output_tokens,
                    "error": None
                }
            except (APIError, Exception) as e:
                error_status = e.status_code if isinstance(e, APIError) else 'N/A'
                if attempt < MAX_RETRIES - 1:
                    print(
                        f"  -> ERROR on job {job_id} (Status: {error_status}, Attempt {attempt + 1}/{MAX_RETRIES}). Retrying...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = (retry_delay * 2) + random.uniform(0, 1)
                else:
                    print(f"  -> FATAL ERROR on job {job_id} (Status: {error_status}). No more retries.")
                    return {
                        "job_id": job_id, "subject": job['subject'], "model": model_name, "prompt_style": prompt_name,
                        "max_points": job['max_points'], "actual_points": job['actual_points'],
                        "ai_evaluation_json": None, "latency_seconds": -1,
                        "input_tokens": None, "output_tokens": None,
                        "error": str(e)
                    }


# --- 3. MAIN ASYNCHRONOUS EXECUTION AND HELPERS ---
async def run_benchmark():
    """Main function to orchestrate the benchmark with per-model concurrency."""
    print("--- Starting Asynchronous Grading Benchmark ---")
    start_total_time = time.monotonic()
    api_key = get_api_key_from_file()
    if not api_key: return
    prompt_templates = load_prompts(PROMPTS_PATH)
    if not prompt_templates: return
    grading_jobs = discover_grading_jobs(DATA_ROOT_PATH)
    if not grading_jobs: return

    semaphore_map = {}
    print("\nConfiguring per-model concurrency limits...")
    for model in MODELS_TO_TEST:
        limit = MODEL_CONFIG.get(model, DEFAULT_CONCURRENCY_LIMIT)
        semaphore_map[model] = asyncio.Semaphore(limit)
        print(f" - {model}: {limit} concurrent requests")

    client = AsyncOpenAI(base_url=BASE_URL, api_key=api_key)
    tasks = []
    total_runs = len(grading_jobs) * len(prompt_templates) * len(MODELS_TO_TEST)
    print(f"\nTotal grading evaluations to perform: {total_runs}")
    print("Creating all tasks...")
    for job in grading_jobs:
        for prompt_name, template in prompt_templates.items():
            for model_name in MODELS_TO_TEST:
                task = grade_task_worker(semaphore_map, client, job, prompt_name, template, model_name)
                tasks.append(task)

    print("All tasks created. Running them concurrently...")
    results = await asyncio.gather(*tasks)
    await client.close()

    final_results = [res for res in results if res]
    print("\nBenchmark complete. Saving results...")
    results_df = pd.DataFrame(final_results)
    results_df.to_csv(RESULTS_FILEPATH, index=False, encoding='utf-8-sig')
    end_total_time = time.monotonic()
    print(f"Results saved to '{RESULTS_FILEPATH}'")
    print(f"Total execution time: {end_total_time - start_total_time:.2f} seconds.")


# --- 4. HELPER FUNCTIONS ---
def get_api_key_from_file():
    try:
        script_location = Path(__file__).resolve().parent
        secret_file_path = script_location.parent / 'secret.txt'
        print(f"Attempting to load API key from: {secret_file_path}")
        api_key = secret_file_path.read_text(encoding='utf-8').strip()
        if not api_key: raise ValueError("'secret.txt' is empty.")
        print("Successfully loaded API key.")
        return api_key
    except (FileNotFoundError, IndexError):
        expected_path = Path(__file__).resolve().parent.parent / 'secret.txt'
        print(
            f"\n--- ERROR ---\nCould not find 'secret.txt'. Please ensure it exists at: {expected_path}\n---------------")
        return None


def load_prompts(prompts_dir):
    templates = {}
    print(f"Loading prompt templates from '{prompts_dir}'...")
    for prompt_style_dir in prompts_dir.iterdir():
        if prompt_style_dir.is_dir():
            style_name = prompt_style_dir.name
            try:
                system_prompt = (prompt_style_dir / "system.md").read_text(encoding='utf-8')
                user_template = (prompt_style_dir / "user.md").read_text(encoding='utf-8')
                templates[style_name] = {"system": system_prompt, "user": user_template}
                print(f" - Loaded prompt style: '{style_name}'")
            except FileNotFoundError:
                print(f" - Warning: Skipping '{style_name}', missing system.md or user.md.")
    return templates


def parse_punkte_file(filepath):
    """
    Parses a Punkte.md or ErhaltenePunkte.md file.
    Supports two formats:
    1. Single number (e.g., "100") for a single task named "Aufgabe".
    2. Multi-task format (e.g., "Nr.1: 10", "a: 8").
    """
    punkte_map = {}
    if not filepath.exists():
        return punkte_map
    try:
        content = filepath.read_text(encoding='utf-8').strip()

        try:
            single_point_value = float(content)
            punkte_map["Aufgabe"] = single_point_value
            return punkte_map
        except (ValueError, TypeError):
            pass

        current_nr_prefix = ""
        for line in content.splitlines():
            line = line.strip()
            if not line: continue

            nr_match = re.match(r"^Nr\.(\d+)\s*$", line)
            if nr_match:
                current_nr_prefix = f"Aufgabe{nr_match.group(1)}"
                continue

            nr_points_match = re.match(r"^Nr\.(\d+):\s*([\d\.]+)", line)
            if nr_points_match:
                punkte_map[f"Aufgabe{nr_points_match.group(1)}"] = float(nr_points_match.group(2))
                current_nr_prefix = ""
                continue

            sub_task_match = re.match(r"^([a-zA-Z]):\s*([\d\.]+)", line)
            if sub_task_match and current_nr_prefix:
                punkte_map[f"{current_nr_prefix}{sub_task_match.group(1)}"] = float(sub_task_match.group(2))
                continue

    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    return punkte_map


def parse_erhaltene_punkte(student_dir):
    return parse_punkte_file(student_dir / "ErhaltenePunkte.md")


def discover_grading_jobs(root_path):
    """Finds all tasks and student answers to create grading jobs."""
    grading_jobs = []
    print("Discovering tasks, student answers, and actual scores...")
    for subject_path in root_path.iterdir():
        if not subject_path.is_dir() or subject_path.name.startswith('_'): continue
        for test_path in subject_path.iterdir():
            if not test_path.is_dir(): continue

            aufg_path = test_path / "Aufgabenstellungen"
            if not aufg_path.exists(): continue

            tasks = {f.stem: f.read_text(encoding='utf-8') for f in aufg_path.glob("Aufgabe*.md")}

            materials_text = "\n\n".join(
                [f"--- {m.stem} ---\n{m.read_text(encoding='utf-8')}"
                 for m in aufg_path.glob("M*.md")])

            max_points_map = parse_punkte_file(aufg_path / "Punkte.md")
            # print(f"DEBUG: Parsed max points for {test_path.relative_to(root_path)}: {max_points_map}")

            if not max_points_map:
                print(
                    f"Warning: Could not parse any points from {aufg_path / 'Punkte.md'}. Skipping all tasks in this test.")
                continue

            for student_dir in test_path.iterdir():
                if student_dir.is_dir() and student_dir.name.startswith("P"):
                    actual_points_map = parse_erhaltene_punkte(student_dir)
                    # print(f"DEBUG: Parsed actual points for {student_dir.relative_to(root_path)}: {actual_points_map}")

                    if not actual_points_map:
                        print(
                            f"Warning: Could not parse any points from {student_dir / 'ErhaltenePunkte.md'}. Skipping this student.")
                        continue

                    for student_answer_file in student_dir.glob("Aufgabe*.md"):
                        task_name = student_answer_file.stem

                        if task_name in tasks:
                            max_points = max_points_map.get(task_name)
                            actual_points = actual_points_map.get(task_name)

                            if max_points is None or actual_points is None:
                                print(
                                    f"Warning: Missing points data for task '{task_name}' in student dir '{student_dir}'. Skipping job.")
                                continue

                            grading_jobs.append({
                                "job_id": f"{subject_path.name}_{test_path.name}_{task_name}_{student_dir.name}",
                                "subject": subject_path.name,
                                "task_name": task_name,
                                "student_answer": student_answer_file.read_text(encoding='utf-8'),
                                "task_text": tasks[task_name],
                                "materials_text": materials_text,
                                "max_points": max_points,
                                "actual_points": actual_points
                            })
    print(f"Found {len(grading_jobs)} individual student answers to grade.")
    return grading_jobs


if __name__ == "__main__":
    asyncio.run(run_benchmark())
