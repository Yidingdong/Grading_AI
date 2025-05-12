import requests
import subprocess
import json
import shlex # Used for safely splitting command strings if needed

# --- Configuration ---
USER_API_BASE_URL = "http://localhost:5000"
COURSE_API_BASE_URL = "http://localhost:5001"
PDF_UPLOADER_CONTAINER = "hlrs-pdf-uploader-1"
# Database configurations are no longer strictly needed for this script version
# but kept here in case you add checks back later or for reference.
MYSQL_CONTAINER = "mysql-server"
MYSQL_USER = "user"
MYSQL_PASSWORD = "password"
MYSQL_DB = "Informations"
MONGO_CONTAINER = "hlrs-mongodb-server-1"
MONGO_USER = "root"
MONGO_PASSWORD = "example"
MONGO_DB = "Exams"

# --- Helper Function for Docker Exec (only needed for PDF upload now) ---
def run_docker_exec(container_name, command_args, capture=True):
    """Runs a command inside a Docker container using docker exec."""
    base_command = ["docker", "exec", container_name]
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

# --- Helper Function for API Calls ---
def make_api_request(method, url, data=None):
    """Makes an API request using the requests library."""
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

        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

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

# --- Test Steps ---

print("=== Starting Test Execution ===")

# 1. Register Users
print("\n=== Step 1: Registering Users ===")
teacher_payload = {"username": "prof_x", "password": "teach123", "name": "Professor X", "user_type": "teacher"}
student1_payload = {"username": "student1", "password": "pass123", "name": "Alice Smith", "user_type": "student"}
student2_payload = {"username": "student2", "password": "pass456", "name": "Bob Johnson", "user_type": "student"}

make_api_request("post", f"{USER_API_BASE_URL}/register", teacher_payload)
make_api_request("post", f"{USER_API_BASE_URL}/register", student1_payload)
make_api_request("post", f"{USER_API_BASE_URL}/register", student2_payload)

# 2. Create a Course
print("\n=== Step 2: Creating a Course ===")
# Assuming teacher prof_x gets ID 1. Fetch ID from response if possible for robustness.
course_payload = {"name": "Advanced Python", "duration_weeks": 16, "teacher_id": 1}
make_api_request("post", f"{COURSE_API_BASE_URL}/courses", course_payload)

# 3. Assign Students to a Course
print("\n=== Step 3: Assigning Students to Course ===")
# Assuming the new course gets ID 1 and students IDs 2, 3. Fetch IDs if possible.
assignment_payload = {"student_ids": [2, 3]}
make_api_request("put", f"{COURSE_API_BASE_URL}/courses/1/students", assignment_payload)

# 4. Upload PDF via Docker Script
print("\n=== Step 4: Uploading PDF via Docker Script ===")
# Note: Ensure the PDF path /app/pdfs/Lorem_ipsum.pdf is correct *inside* the container
pdf_upload_cmd = [
    "python", "pdf_to_mongodb.py",
    "--pdf", "/app/pdfs/Microsoft_Certificate.pdf",
    "--username", "teacher_alice", # Adjust if needed
    "--course", "IT 102",         # Adjust if needed
    "--student-name", "John Doe", # Adjust if needed
    "--student-id", "S123",       # Adjust if needed
    "--teacher", "prof_x",
    "--category", "answer_sheet"
]
run_docker_exec(PDF_UPLOADER_CONTAINER, pdf_upload_cmd)

print("\n=== Test Execution Finished ===")
print("=== Run python verify.py to verify ===")