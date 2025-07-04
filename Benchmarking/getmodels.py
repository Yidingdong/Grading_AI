import os
import time
import pandas as pd
import requests
from openai import OpenAI
from pathlib import Path

# --- 1. CONFIGURATION ---
DATA_ROOT_PATH = Path("./DataCollection")

RESULTS_FILEPATH = Path("./benchmark_results.csv")

MODELS_TO_EXCLUDE = ["auto", "smallest-chat-model"]

BASE_URL = "https://api.seedbox.ai"



def get_api_key_from_file():
    try:
        script_location = Path(__file__).resolve()
        project_root = script_location.parents[2]
        secret_file_path = project_root / 'secret.txt'

        print(f"Attempting to load API key from: {secret_file_path}")

        api_key = secret_file_path.read_text(encoding='utf-8').strip()

        if not api_key:
            raise ValueError("The 'secret.txt' file is empty.")

        print("Successfully loaded API key.")
        return api_key
    except (FileNotFoundError, IndexError):
        print("\n--- ERROR ---")
        print("Could not find 'secret.txt'.")
        print(f"Please ensure 'secret.txt' exists at this location: {project_root / 'secret.txt'}")
        print("---------------")
        return None
    except Exception as e:
        print(f"An error occurred while reading the API key: {e}")
        return None


def get_and_filter_models():
    print("Fetching available models from Seedbox API...")
    try:
        url = f"{BASE_URL}/models"
        response = requests.get(url)
        response.raise_for_status()

        all_models = response.json().get("chat_models", [])
        if not all_models:
            print("Warning: No chat models found in API response.")
            return []

        print(f"Found {len(all_models)} chat models.")

        # Filter the list
        models_to_test = [
            model for model in all_models if model not in MODELS_TO_EXCLUDE
        ]

        print(f"Excluding: {MODELS_TO_EXCLUDE}")
        print(f"Will run benchmark on {len(models_to_test)} models: {models_to_test}")
        return models_to_test

    except requests.exceptions.RequestException as e:
        print(f"Error fetching models: {e}")
        return []



def create_simple_prompt(task_details):
    """A direct, no-frills prompt."""
    task_text = task_details['task_text']
    materials_text = task_details['materials_text']
    prompt_content = f"Aufgabenstellung:\n{task_text}\n\n"
    if materials_text:
        prompt_content += f"Verfügbare Materialien:\n{materials_text}"
    return [{"role": "user", "content": prompt_content}]


def create_persona_prompt(task_details):
    task_text = task_details['task_text']
    materials_text = task_details['materials_text']
    subject = task_details['subject']
    level = "Leistungskurs" if subject in ["Chemie", "Wirtschaft"] else "Basiskurs"
    system_message = (
        f"Du bist ein Schüler der 11. Klasse eines deutschen G8-Gymnasiums. "
        f"Deine Aufgabe ist es, eine Klausuraufgabe im Fach {subject} auf {level}-Niveau zu beantworten. "
        "Antworte klar, strukturiert und ausschließlich auf Deutsch. Nutze nur die bereitgestellten Materialien."
    )
    prompt_content = f"Hier ist die Aufgabenstellung:\n---\n{task_text}\n---\n"
    if materials_text:
        prompt_content += f"\nNutze für deine Antwort die folgenden Materialien:\n{materials_text}"
    return [{"role": "system", "content": system_message}, {"role": "user", "content": prompt_content}]


PROMPT_TEMPLATES = {
    "simple_prompt": create_simple_prompt,
    "persona_prompt": create_persona_prompt,
}


# --- 4. CORE SCRIPT LOGIC (Unchanged) ---

def read_file_content(filepath):
    try:
        return filepath.read_text(encoding='utf-8')
    except FileNotFoundError:
        print(f"Warning: File not found at {filepath}")
        return ""


def discover_tasks(root_path):
    tasks = []
    for subject_path in root_path.iterdir():
        if not subject_path.is_dir(): continue
        for test_path in subject_path.iterdir():
            if not test_path.is_dir(): continue
            aufg_path = test_path / "Aufgabenstellungen"
            if not aufg_path.exists(): continue
            materials = {m.stem: read_file_content(m) for m in aufg_path.glob("M*.md")}
            materials_text = "\n\n".join([f"--- {n} ---\n{c}" for n, c in materials.items()])
            for task_file in aufg_path.glob("Aufgabe*.md"):
                tasks.append({
                    "task_id": f"{subject_path.name}_{test_path.name}_{task_file.stem}",
                    "subject": subject_path.name,
                    "test_name": test_path.name,
                    "task_text": read_file_content(task_file),
                    "materials_text": materials_text,
                })
    return tasks


def run_benchmark():
    """Main function to run the entire benchmarking process."""
    print("--- Starting Benchmark ---")

    api_key = get_api_key_from_file()
    if not api_key:
        return

    models_to_test = get_and_filter_models()
    if not models_to_test:
        print("No models to test. Exiting.")
        return

    tasks_to_run = discover_tasks(DATA_ROOT_PATH)
    if not tasks_to_run:
        print(f"Error: No tasks found in '{DATA_ROOT_PATH}'. Check the path.")
        return
    print(f"Discovered {len(tasks_to_run)} tasks.")

    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    results = []
    total_runs = len(tasks_to_run) * len(PROMPT_TEMPLATES) * len(models_to_test)
    current_run = 0
    print(f"\nTotal API calls to be made: {total_runs}")

    for task in tasks_to_run:
        for prompt_name, prompt_function in PROMPT_TEMPLATES.items():
            messages = prompt_function(task)
            for model_name in models_to_test:
                current_run += 1
                print(f"[{current_run}/{total_runs}] Running Test: "
                      f"Task={task['task_id']}, Prompt={prompt_name}, Model={model_name}")

                try:
                    start_time = time.monotonic()
                    completion = client.chat.completions.create(model=model_name, messages=messages)
                    end_time = time.monotonic()

                    results.append({
                        "task_id": task['task_id'], "subject": task['subject'],
                        "model": model_name, "prompt_style": prompt_name,
                        "ai_answer": completion.choices[0].message.content,
                        "latency_seconds": end_time - start_time,
                        "input_tokens": completion.usage.prompt_tokens,
                        "output_tokens": completion.usage.completion_tokens,
                        "error": None
                    })
                    print(f"  -> Success! Latency: {end_time - start_time:.2f}s")
                except Exception as e:
                    print(f"  -> ERROR: {e}")
                    results.append({
                        "task_id": task['task_id'], "subject": task['subject'],
                        "model": model_name, "prompt_style": prompt_name,
                        "ai_answer": None, "latency_seconds": -1,
                        "input_tokens": None, "output_tokens": None, "error": str(e)
                    })

    print("\nBenchmark complete. Saving results...")
    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULTS_FILEPATH, index=False, encoding='utf-8-sig')
    print(f"Results saved to '{RESULTS_FILEPATH}'")


if __name__ == "__main__":
    run_benchmark()