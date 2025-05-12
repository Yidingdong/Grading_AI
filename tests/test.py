import requests
import subprocess
import json
import shlex # Used for safely splitting command strings if needed
import time
import sys # To exit if services don't come up

# --- Configuration ---
USER_API_BASE_URL = "http://localhost:5000"
COURSE_API_BASE_URL = "http://localhost:5001"
PDF_UPLOADER_CONTAINER = "hlrs-pdf-uploader-1" # Ensure this matches your compose file if changed
# Database configurations are no longer strictly needed for this script version
# but kept here in case you add checks back later or for reference.
MYSQL_CONTAINER = "mysql-server"
MYSQL_USER = "user"
MYSQL_PASSWORD = "password"
MYSQL_DB = "Informations"
MONGO_CONTAINER = "hlrs-mongodb-server-1" # Ensure this matches your compose file if changed
MONGO_USER = "root"
MONGO_PASSWORD = "example"
MONGO_DB = "Exams"

# --- Helper Function to Wait for Services ---
def wait_for_service(url, service_name, timeout=120):
    """Polls a service URL until it responds or timeout occurs."""
    print(f"Waiting for {service_name} at {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Use a simple GET request to check if the root is reachable
            # Adjust path if '/' is not a valid route (e.g., use '/health')
            response = requests.get(url, timeout=5)
            # Check for any successful status code (2xx or maybe 404 if root isn't defined)
            # Or specifically check if it's NOT a connection error
            print(f"{service_name} responded with status {response.status_code}. Ready.")
            return True # Service is up
        except requests.exceptions.ConnectionError:
            print(f".", end='', flush=True) # Print progress dots
            time.sleep(3) # Wait before retrying
        except requests.exceptions.Timeout:
            print(f"T", end='', flush=True) # Indicate timeout on check
            time.sleep(3)
        except requests.exceptions.RequestException as e:
            print(f"\nUnexpected error while checking {service_name}: {e}")
            time.sleep(3)

    print(f"\nError: Timeout waiting for {service_name} at {url} after {timeout} seconds.")
    return False # Service did not become ready

# --- Helper Function for Docker Exec ---
def run_docker_exec(container_name, command_args, capture=True):
    """Runs a command inside a Docker container using docker exec."""
    # Find the actual container name (handles potential renaming by compose)
    try:
        find_cmd = ["docker", "compose", "ps", "-q", container_name]
        print(f"\n--- Finding container ID for service '{container_name}' ---")
        print(f"Command: {' '.join(shlex.quote(str(arg)) for arg in find_cmd)}")
        process = subprocess.run(find_cmd, capture_output=True, text=True, check=True)
        actual_container_id = process.stdout.strip()
        if not actual_container_id:
            print(f"!!! Error: Could not find running container for service '{container_name}' !!!")
            raise ValueError(f"Service {container_name} not found or not running.")
        print(f"Found container ID: {actual_container_id}")
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print(f"!!! Failed to get container ID: {e} !!!")
        raise

    base_command = ["docker", "exec", actual_container_id] # Use found ID
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

# --- Main Test Execution ---
print("======== Starting Test Script ========")

# Wait for dependent services to be ready
registration_ready = wait_for_service(USER_API_BASE_URL, "Registration Service")
course_ready = wait_for_service(COURSE_API_BASE_URL, "Course Allocation Service")

if not registration_ready or not course_ready:
    print("\n!!! Required services did not become available. Aborting tests. !!!")
    sys.exit(1) # Exit script with error code

print("\n=== All required API services are ready. Starting Test Execution ===")


# 1. Register Users
print("\n=== Step 1: Registering Users ===")
teacher_payload = {"username": "prof_x", "password": "teach123", "name": "Professor X", "user_type": "teacher"}
student1_payload = {"username": "student1", "password": "pass123", "name": "Alice Smith", "user_type": "student"}
student2_payload = {"username": "student2", "password": "pass456", "name": "Bob Johnson", "user_type": "student"}

try: # Added try block for better error handling during tests
    make_api_request("post", f"{USER_API_BASE_URL}/register", teacher_payload)
    make_api_request("post", f"{USER_API_BASE_URL}/register", student1_payload)
    make_api_request("post", f"{USER_API_BASE_URL}/register", student2_payload)

    # 2. Create a Course
    print("\n=== Step 2: Creating a Course ===")
    # Assuming teacher prof_x gets ID 1. Ideally, fetch ID from response.
    course_payload = {"name": "Advanced Python", "duration_weeks": 16, "teacher_id": 1}
    course_response = make_api_request("post", f"{COURSE_API_BASE_URL}/courses", course_payload)
    # You could extract the course_id here if needed: course_id = course_response.json().get('course_id', 1)

    # 3. Assign Students to a Course
    print("\n=== Step 3: Assigning Students to Course ===")
    # Assuming the new course gets ID 1 and students IDs 2, 3. Fetch IDs if possible.
    assignment_payload = {"student_ids": [2, 3]}
    make_api_request("put", f"{COURSE_API_BASE_URL}/courses/1/students", assignment_payload) # Using hardcoded course ID 1 for now

    # 4. Upload PDF via Docker Script
    print("\n=== Step 4: Uploading PDF via Docker Script ===")
    # Note: Ensure the PDF path /app/pdfs/Lorem_ipsum.pdf is correct *inside* the container
    # Also update the service name if you changed it in docker-compose.yml
    pdf_upload_cmd = [
        "python", "pdf_to_mongodb.py",
        "--pdf", "/app/pdfs/Lorem_ipsum.pdf", # Path inside the container
        "--username", "student1", # Using registered student username
        "--course", "Advanced Python", # Using created course name
        "--student-name", "Alice Smith", # Matching registered student
        "--student-id", "2",       # Using assumed student ID
        "--teacher", "prof_x",     # Using registered teacher username
        "--category", "answer_sheet"
    ]
    # Use the service name from docker-compose.yml for the container lookup
    run_docker_exec("pdf-uploader", pdf_upload_cmd)

    print("\n=== Test Execution Finished Successfully ===")
    print("=== Run python verify.py to check database state ===")

except Exception as e:
    print(f"\n!!! An error occurred during test execution: {e} !!!")
    print("=== Test Execution Failed ===")
    sys.exit(1) # Exit with error