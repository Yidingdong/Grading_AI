import requests
import subprocess
import json
import shlex
import time
import sys

USER_API_BASE_URL = "http://localhost:5000"
COURSE_API_BASE_URL = "http://localhost:5001"
PDF_UPLOADER_SERVICE_NAME = "pdf-uploader"

MYSQL_CONTAINER = "mysql-server"
MYSQL_USER = "user"
MYSQL_PASSWORD = "password"
MYSQL_DB = "Informations"
MONGO_CONTAINER = "hlrs-mongodb-server-1"
MONGO_USER = "root"
MONGO_PASSWORD = "example"
MONGO_DB = "Exams"

def wait_for_service(url, service_name, timeout=120):
    print(f"Waiting for {service_name} at {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            print(f"{service_name} responded with status {response.status_code}. Ready.")
            return True
        except requests.exceptions.ConnectionError:
            print(f".", end='', flush=True)
            time.sleep(3)
        except requests.exceptions.Timeout:
            print(f"T", end='', flush=True)
            time.sleep(3)
        except requests.exceptions.RequestException as e:
            print(f"\nUnexpected error while checking {service_name}: {e}")
            time.sleep(3)

    print(f"\nError: Timeout waiting for {service_name} at {url} after {timeout} seconds.")
    return False

def run_docker_exec(service_name, command_args, capture=True):
    try:
        find_cmd = ["docker", "compose", "ps", "-q", service_name]
        print(f"\n--- Finding container ID for service '{service_name}' ---")
        print(f"Command: {' '.join(shlex.quote(str(arg)) for arg in find_cmd)}")
        process = subprocess.run(find_cmd, capture_output=True, text=True, check=True)
        actual_container_id = process.stdout.strip()
        if not actual_container_id:
            print(f"!!! Error: Could not find running container for service '{service_name}' !!!")
            raise ValueError(f"Service {service_name} not found or not running.")
        print(f"Found container ID: {actual_container_id}")
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print(f"!!! Failed to get container ID: {e} !!!")
        raise

    base_command = ["docker", "exec", actual_container_id]
    full_command = base_command + command_args
    print(f"\n--- Running Docker Command ---")
    print(f"Command: {' '.join(shlex.quote(str(arg)) for arg in full_command)}")
    try:
        result = subprocess.run(full_command, capture_output=capture, text=True, check=True)
        if capture:
            print("--- Docker Command Output ---")
            if result.stdout:
                print("STDOUT:")
                print(result.stdout.strip())
            if result.stderr:
                print("STDERR:")
                print(result.stderr.strip())
            print("--- Docker Command End ---")
        return result.stdout, result.stderr
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

def make_api_request(method, url, data=None):
    print(f"\n--- Making API Request ---")
    print(f"Method: {method.upper()}")
    print(f"URL: {url}")
    if data:
        print(f"Data: {json.dumps(data)}")

    headers = {'Content-Type': 'application/json'}
    try:
        if method.lower() == 'post':
            response = requests.post(url, json=data, headers=headers, timeout=10)
        elif method.lower() == 'put':
            response = requests.put(url, json=data, headers=headers, timeout=10)
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
        print(f"!!! API Connection Error: Could not connect to {url}. Is the service running? !!!")
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
course_ready = wait_for_service(COURSE_API_BASE_URL, "Course Allocation Service")

if not registration_ready or not course_ready:
    print("\n!!! Required services did not become available. Aborting tests. !!!")
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

    print("\n=== Step 3: Assigning Students to Course ===")
    assignment_payload = {"student_ids": [2, 3]}
    make_api_request("put", f"{COURSE_API_BASE_URL}/courses/1/students", assignment_payload)

    print("\n=== Step 4: Uploading Lorem Ipsum OCR PDF via Docker Script ===")
    pdf_upload_cmd = [
        "python", "pdf_to_mongodb.py",
        "--pdf", "/app/pdfs/Lorem_ipsum_OCR_Version.pdf", # Changed filename
        "--username", "student2", # Using different student for variation
        "--course", "Advanced Python",
        "--student-name", "Bob Johnson", # Matching student2
        "--student-id", "3", # Matching student2 ID
        "--teacher", "prof_x",
        "--category", "answer_sheet", # Changed category
        "--lang", "eng" # Explicitly set to English (default)
    ]
    run_docker_exec(PDF_UPLOADER_SERVICE_NAME, pdf_upload_cmd)

    print("\n=== Test Execution Finished Successfully ===")
    print("=== Run python verify.py to check database state ===")

except Exception as e:
    print(f"\n!!! An error occurred during test execution: {e} !!!")
    print("=== Test Execution Failed ===")
    sys.exit(1)