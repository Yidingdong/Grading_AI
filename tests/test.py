import requests
import subprocess
import json
import shlex
import time
import sys
import re

USER_API_BASE_URL = "http://localhost:5000"
COURSE_API_BASE_URL = "http://localhost:5001"
OLLAMA_API_BASE_URL = "http://localhost:11434"
GRADING_API_BASE_URL = "http://localhost:5002"
PDF_UPLOADER_SERVICE_NAME = "pdf-uploader"

MYSQL_CONTAINER = "mysql-server"
MYSQL_USER = "user"
MYSQL_PASSWORD = "password"
MYSQL_DB = "Informations"
MONGO_CONTAINER = "hlrs-mongodb-server-1"
MONGO_USER = "root"
MONGO_PASSWORD = "example"
MONGO_DB = "Exams"

OLLAMA_TEST_MODEL = "granite3.2-vision:latest"
LOREM_IPSUM_MONGO_ID = None


def wait_for_service(url, service_name, timeout=120, health_path="/health", is_ollama=False):
    print(f"Waiting for {service_name} at {url}...")
    start_time = time.time()
    check_url = f"{url}{health_path}"
    if is_ollama:
        check_url = f"{url}/api/tags"

    while time.time() - start_time < timeout:
        try:
            response = requests.get(check_url, timeout=10)
            if is_ollama:
                if response.status_code == 200:
                    try:
                        models = response.json().get("models", [])
                        if any(m.get("name") == OLLAMA_TEST_MODEL for m in models):
                            print(f"\n{service_name} is up and model '{OLLAMA_TEST_MODEL}' is available.")
                            return True
                        else:
                            print(f".(Ollama up, model {OLLAMA_TEST_MODEL} not yet listed)", end='', flush=True)
                    except json.JSONDecodeError:
                        print(f".(Ollama up, but /api/tags response not JSON)", end='', flush=True)
                else:
                    print(f".(Ollama status {response.status_code})", end='', flush=True)

            elif response.status_code == 200:
                print(f"\n{service_name} responded with status {response.status_code}. Ready.")
                return True
            else:
                print(f".(status {response.status_code})", end='', flush=True)

        except requests.exceptions.ConnectionError:
            print(f".", end='', flush=True)
        except requests.exceptions.Timeout:
            print(f"T", end='', flush=True)
        except requests.exceptions.RequestException as e:
            print(f"\nUnexpected error while checking {service_name}: {e}")

        time.sleep(5)

    print(
        f"\nError: Timeout waiting for {service_name} (or model {OLLAMA_TEST_MODEL} for Ollama) at {url} after {timeout} seconds.")
    return False


def run_docker_exec(service_name, command_args, capture=True):
    base_command = ["docker", "compose", "exec", service_name]
    full_command = base_command + command_args
    print(f"\n--- Running Docker Command ---")
    print(f"Command: {' '.join(shlex.quote(str(arg)) for arg in full_command)}")
    try:
        result = subprocess.run(full_command, capture_output=capture, text=True, check=True, encoding='utf-8')
        if capture:
            print("--- Docker Command Output ---")
            # pdf_to_mongodb.py now uses logging, which might go to stderr by default in Docker exec
            # if not explicitly configured for stdout.
            # We will print both stdout and stderr to catch the logs.
            if result.stdout:
                print("STDOUT:")
                print(result.stdout.strip())
            if result.stderr:
                print("STDERR:")  # Logs from pdf_to_mongodb might appear here
                print(result.stderr.strip())
            print("--- Docker Command End ---")
        return result
    except subprocess.CalledProcessError as e:
        print(f"!!! Docker command failed with exit code {e.returncode} !!!")
        if e.stdout: print("STDOUT:\n", e.stdout.strip())
        if e.stderr: print("STDERR:\n", e.stderr.strip())
        raise
    except FileNotFoundError:
        print("!!! Error: 'docker' command not found. Is Docker installed and in PATH? !!!")
        raise
    except Exception as e:
        print(f"!!! An unexpected error occurred running docker exec: {e} !!!")
        raise


def make_api_request(method, url, data=None, headers=None, timeout=30):
    print(f"\n--- Making API Request ---")
    print(f"Method: {method.upper()}")
    print(f"URL: {url}")
    if data:
        print(f"Data: {json.dumps(data)}")

    if headers is None:
        headers = {'Content-Type': 'application/json'}
    else:
        if data and 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

    try:
        if method.lower() == 'get':
            response = requests.get(url, headers=headers, timeout=timeout)
        elif method.lower() == 'post':
            response = requests.post(url, json=data, headers=headers, timeout=timeout)
        elif method.lower() == 'put':
            response = requests.put(url, json=data, headers=headers, timeout=timeout)
        else:
            print(f"Unsupported HTTP method: {method}")
            return None

        response.raise_for_status()

        print(f"Response Status Code: {response.status_code}")
        try:
            print(f"Response Body: {response.json()}")
        except json.JSONDecodeError:
            print(f"Response Body (non-JSON): {response.text}")
        print("--- API Request End ---")
        return response

    except requests.exceptions.ConnectionError as e:
        print(f"!!! API Connection Error: Could not connect to {url}. Is the service running and port exposed? !!!")
        print(f"Error details: {e}")
        raise
    except requests.exceptions.Timeout:
        print(f"!!! API Request Timeout: The request to {url} timed out. !!!")
        raise
    except requests.exceptions.RequestException as e:
        print(f"!!! API Request Failed: {e} !!!")
        if e.response is not None:
            print(f"Response Status Code: {e.response.status_code}")
            print(f"Response Body: {e.response.text}")
        raise


print("======== Starting Test Script ========")

registration_ready = wait_for_service(USER_API_BASE_URL, "Registration Service")
course_ready = wait_for_service(COURSE_API_BASE_URL, "Course Allocation Service", health_path="/health")
ollama_ready = wait_for_service(OLLAMA_API_BASE_URL, "Ollama AI Service", timeout=600, is_ollama=True)
grading_ready = wait_for_service(GRADING_API_BASE_URL, "Grading Service", health_path="/health")

if not registration_ready or not course_ready or not ollama_ready or not grading_ready:
    print("\n!!! One or more required services did not become available. Aborting tests. !!!")
    sys.exit(1)

print("\n=== All required API services are ready. Starting Test Execution ===")

try:
    print("\n=== Step 1: Registering Users ===")
    teacher_payload = {"username": "prof_x", "password": "teach123", "name": "Professor X", "user_type": "teacher"}
    student1_payload = {"username": "student1", "password": "pass123", "name": "Alice Smith", "user_type": "student"}
    student2_payload = {"username": "student2", "password": "pass456", "name": "Bob Johnson", "user_type": "student"}

    make_api_request("post", f"{USER_API_BASE_URL}/register", teacher_payload)
    make_api_request("post", f"{USER_API_BASE_URL}/register", student1_payload)
    make_api_request("post", f"{USER_API_BASE_URL}/register", student2_payload)

    print("\n=== Step 2: Creating a Course ===")
    course_payload = {"name": "Advanced Python", "duration_weeks": 16, "teacher_id": 1}
    course_response = make_api_request("post", f"{COURSE_API_BASE_URL}/courses", course_payload)
    course_id = course_response.json().get('course_id')
    if not course_id:
        raise ValueError("Failed to get course_id from course creation response.")

    print("\n=== Step 3: Assigning Students to Course ===")
    assignment_payload = {"student_ids": [2, 3]}
    make_api_request("put", f"{COURSE_API_BASE_URL}/courses/{course_id}/students", assignment_payload)

    print("\n=== Step 4: Uploading Lorem Ipsum OCR PDF via Docker Script ===")
    pdf_upload_cmd_lorem = [
        "python", "pdf_to_mongodb.py",
        "--pdf", "/app/pdfs/Lorem_ipsum_OCR_Version.pdf",
        "--username", "student2",
        "--course", "Advanced Python",
        "--student-name", "Bob Johnson",
        "--student-id", "3",
        "--teacher", "prof_x",
        "--category", "answer_sheet",
        "--lang", "eng",
        "--ocr-dpi", "300"
    ]
    lorem_upload_result = run_docker_exec(PDF_UPLOADER_SERVICE_NAME, pdf_upload_cmd_lorem)

    output_to_search = lorem_upload_result.stdout + "\n" + lorem_upload_result.stderr
    match = re.search(r"Submission ID: ([0-9a-fA-F]+)", output_to_search)
    if match:
        LOREM_IPSUM_MONGO_ID = match.group(1)
        print(f"Captured Lorem Ipsum MongoDB ID: {LOREM_IPSUM_MONGO_ID}")
    else:
        print("Warning: Could not parse Lorem Ipsum MongoDB ID from pdf_uploader output.")
        print(f"Combined STDOUT/STDERR from pdf_uploader:\n{output_to_search}")

    print("\n=== Step 5: Uploading StGB Auszug PDF (Reference Material) ===")
    stgb_pdf_upload_cmd = [
        "python", "pdf_to_mongodb.py",
        "--pdf", "/app/pdfs/StGB_Auszug.pdf",
        "--username", "prof_x",
        "--course", "Advanced Python",
        "--student-name", "N/A",
        "--teacher", "prof_x",
        "--category", "reference_material",
        "--lang", "deu",
        "--ocr-dpi", "300"
    ]
    run_docker_exec(PDF_UPLOADER_SERVICE_NAME, stgb_pdf_upload_cmd)

    print("\n=== Step 6: Testing Ollama AI Service (Directly) ===")
    ollama_payload = {
        "model": OLLAMA_TEST_MODEL,
        "prompt": "What is 2+2?",
        "stream": False
    }
    ollama_response = make_api_request("post", f"{OLLAMA_API_BASE_URL}/api/generate", data=ollama_payload, timeout=60)
    if ollama_response and ollama_response.json().get("response"):
        print(f"Ollama generated response: {ollama_response.json()['response'][:100]}...")
    else:
        raise ValueError("Ollama did not return a valid response.")

    print("\n=== Step 7: Testing Grading Service ===")
    if LOREM_IPSUM_MONGO_ID:
        grading_payload = {"document_id": LOREM_IPSUM_MONGO_ID}
        grading_response = make_api_request("post", f"{GRADING_API_BASE_URL}/grade_document", data=grading_payload,
                                            timeout=180)
        if grading_response and grading_response.json().get("evaluation_result"):
            print(f"Grading service evaluation: {grading_response.json()['evaluation_result'][:200]}...")
        else:
            raise ValueError("Grading service did not return a valid evaluation.")
    else:
        print("Skipping Grading Service test as LOREM_IPSUM_MONGO_ID was not captured.")

    print("\n=== Test Execution Finished Successfully ===")
    print("=== Run python verify.py to check database state and Ollama model list ===")

except Exception as e:
    print(f"\n!!! An error occurred during test execution: {type(e).__name__} - {e} !!!")
    import traceback

    traceback.print_exc()
    print("=== Test Execution Failed ===")
    sys.exit(1)