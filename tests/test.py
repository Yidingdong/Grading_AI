import requests
import subprocess
import json
import shlex
import time
import sys
import re
import mysql.connector  # For fetching IDs
from pymongo import MongoClient  # For cleanup
from bson import ObjectId  # For cleanup

# --- Configuration ---
USER_API_BASE_URL = "http://localhost:5000"  # registration-service
COURSE_API_BASE_URL = "http://localhost:5001"  # course-allocation-service
OLLAMA_API_BASE_URL = "http://localhost:11434"  # ollama-service
GRADING_API_BASE_URL = "http://localhost:5002"  # grading-service
PDF_PROCESSOR_API_BASE_URL = "http://localhost:5003"  # pdf-processor-service
PDF_PROCESSOR_CONTAINER_NAME = "pdf-processor-app"  # As defined in docker-compose

OLLAMA_TEST_MODEL = "granite3.2-vision:latest"

# MySQL connection details
MYSQL_HOST = "localhost"
MYSQL_USER = "user"
MYSQL_PASSWORD = "password"
MYSQL_DATABASE = "Informations"

# MongoDB connection details FOR CLEANUP
MONGO_HOST = "localhost"
MONGO_PORT = 27017
MONGO_ROOT_USER = "root"
MONGO_ROOT_PASSWORD = "example"
MONGO_EXAMS_DB_NAME = "Exams"
MONGO_PDF_SUBMISSIONS_COLLECTION = "pdf_submissions"

# Global variables to store fetched IDs
TEACHER_USERNAME = "test_teacher_dyn"
STUDENT1_USERNAME = "test_student1_dyn"
STUDENT2_USERNAME = "test_student2_dyn"

TEACHER_DB_ID = None
STUDENT1_DB_ID = None
STUDENT2_DB_ID = None
COURSE_ID_GLOBAL = None
LOREM_IPSUM_OCR_EXAMS_ID = None


# --- Helper Functions ---
def wait_for_service(url, service_name, timeout=180, health_path="/health", is_ollama=False):
    print(f"Waiting for {service_name} at {url} (timeout: {timeout}s)...")
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
                        models_data = response.json()
                        if any(m.get("name") == OLLAMA_TEST_MODEL for m in models_data.get("models", [])):
                            print(f"\nSUCCESS: {service_name} is up and model '{OLLAMA_TEST_MODEL}' is available.")
                            return True
                        else:
                            print(f".(Ollama up, model {OLLAMA_TEST_MODEL} not yet listed)", end='', flush=True)
                    except json.JSONDecodeError:
                        print(f".(Ollama up, but {check_url} response not JSON)", end='', flush=True)
                else:
                    print(f".(Ollama status {response.status_code})", end='', flush=True)
            elif response.status_code == 200:
                print(f"\nSUCCESS: {service_name} responded with status {response.status_code}. Ready.")
                return True
            else:
                print(f".(status {response.status_code})", end='', flush=True)
        except requests.exceptions.ConnectionError:
            print(".", end='', flush=True)
        except requests.exceptions.Timeout:
            print("T", end='', flush=True)
        except requests.exceptions.RequestException as e:
            print(f"\nError checking {service_name} @ {check_url}: {e}")
        time.sleep(5)
    print(f"\nFAILURE: Timeout waiting for {service_name} at {url} after {timeout} seconds.")
    return False


def make_api_request(method, url, data=None, headers=None, timeout=30, description="API Request", expect_json=True):
    print(f"\n--- Making {description} ---")
    print(f"Method: {method.upper()}, URL: {url}")
    if data: print(f"Data: {json.dumps(data)}")

    final_headers = {'Content-Type': 'application/json'}
    if headers:
        final_headers.update(headers)

    try:
        response = requests.request(method, url, json=data if method.lower() not in ['get', 'delete'] else None,
                                    params=data if method.lower() == 'get' else None, headers=final_headers,
                                    timeout=timeout)
        response_body_text = "N/A"
        response_body_json = None
        try:
            if expect_json and response.content:
                response_body_json = response.json()
                response_body_text = json.dumps(response_body_json)
            elif response.content:
                response_body_text = response.text
        except json.JSONDecodeError:
            response_body_text = response.text
            if expect_json:
                print(f"Warning: Expected JSON response but got: {response_body_text[:200]}")

        print(f"Response Status: {response.status_code}, Body: {response_body_text[:500]}...")
        response.raise_for_status()  # Will raise HTTPError for bad responses (4xx or 5xx)
        print(f"--- {description} Successful ---")
        return response
    except requests.exceptions.HTTPError as e:
        print(f"!!! {description} HTTP Error: {e.response.status_code} - {e.response.text[:500]} !!!")
        raise
    except requests.exceptions.RequestException as e:
        print(f"!!! {description} Failed: {e} !!!")
        raise


def get_user_id_by_username(username):
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD,
                                       database=MYSQL_DATABASE)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user:
            print(f"Successfully fetched ID for username '{username}': {user['id']}")
            return user['id']
        else:
            print(f"Warning: Could not find user with username '{username}' in the database.")
            return None
    except mysql.connector.Error as err:
        print(f"!!! MySQL error fetching ID for '{username}': {err} !!!")
        raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def run_docker_exec_pdf_processor_cli(container_name, pdf_path_in_container, username, course, student_name, student_id,
                                      teacher_username, category, lang="eng"):
    command_args = [
        "python", "pdf_to_mongodb.py",
        "--pdf", pdf_path_in_container,
        "--username", username,
        "--course", course,
        "--student-name", student_name,
        "--teacher", teacher_username,
        "--category", category,
        "--lang", lang
    ]
    if student_id:
        command_args.extend(["--student-id", str(student_id)])

    base_command = ["docker", "exec", container_name]
    full_command = base_command + command_args
    print(f"\n--- Running Docker Exec (CLI PDF Processing for Setup) ---")
    print(f"Command: {' '.join(shlex.quote(str(arg)) for arg in full_command)}")
    try:
        result = subprocess.run(full_command, capture_output=True, text=True, check=False, encoding='utf-8')
        output_to_search = result.stdout + "\n" + result.stderr  # Combine both for searching
        print("--- Docker Exec Output ---")
        print("STDOUT:\n", result.stdout.strip() if result.stdout else " (empty)")
        print("STDERR:\n", result.stderr.strip() if result.stderr else " (empty)")
        print("--- Docker Exec End ---")

        if result.returncode != 0:
            print(
                f"Warning: Docker exec CLI PDF processing had a non-zero exit code ({result.returncode}). Will still try to parse ID.")

        match_new_id = re.search(r"Submission ID: ([0-9a-fA-F]{24})", output_to_search)
        if match_new_id:
            print(f"Found New Submission ID from CLI output: {match_new_id.group(1)}")
            return match_new_id.group(1)

        match_existing_id = re.search(r"Returning existing Exams DB ID: ([0-9a-fA-F]{24})", output_to_search)
        if match_existing_id:
            print(f"Found Existing Submission ID from CLI output: {match_existing_id.group(1)}")
            return match_existing_id.group(1)

        print("!!! Could not find Submission ID in CLI output. !!!")
        if result.returncode != 0:  # If no ID found AND it errored, then raise
            raise subprocess.CalledProcessError(result.returncode, full_command, output=result.stdout,
                                                stderr=result.stderr)
        return None  # If no ID found but exit code was 0, return None
    except Exception as e:
        print(f"!!! Unexpected error during Docker exec CLI PDF processing: {e} !!!")
        raise


def cleanup_test_data():
    global TEACHER_DB_ID, STUDENT1_DB_ID, STUDENT2_DB_ID, COURSE_ID_GLOBAL, LOREM_IPSUM_OCR_EXAMS_ID
    print("\n--- Starting Test Data Cleanup ---")
    mysql_conn = None
    mysql_cursor = None
    mongo_client_cleanup = None
    try:
        # MySQL Cleanup
        print("Attempting MySQL cleanup...")
        mysql_conn = mysql.connector.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD,
                                             database=MYSQL_DATABASE, connection_timeout=5)
        mysql_cursor = mysql_conn.cursor()

        # Order of deletion matters due to foreign key constraints
        # 1. Delete enrollments
        if COURSE_ID_GLOBAL:
            mysql_cursor.execute("DELETE FROM student_course WHERE course_id = %s", (COURSE_ID_GLOBAL,))
            print(f"Deleted enrollments for course ID {COURSE_ID_GLOBAL}")

        # 2. Delete courses
        if COURSE_ID_GLOBAL:
            mysql_cursor.execute("DELETE FROM courses WHERE course_id = %s", (COURSE_ID_GLOBAL,))
            print(f"Deleted course with ID {COURSE_ID_GLOBAL}")
            COURSE_ID_GLOBAL = None  # Clear after deletion

        # 3. Delete users
        user_ids_to_delete = []
        if TEACHER_DB_ID: user_ids_to_delete.append(TEACHER_DB_ID)
        if STUDENT1_DB_ID: user_ids_to_delete.append(STUDENT1_DB_ID)
        if STUDENT2_DB_ID: user_ids_to_delete.append(STUDENT2_DB_ID)

        for user_id in user_ids_to_delete:
            # Must ensure courses taught by teacher are deleted or teacher_id nullable/set to null
            # For this test, we assume the course taught by TEACHER_DB_ID was COURSE_ID_GLOBAL and deleted
            mysql_cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            print(f"Deleted user with ID {user_id}")

        mysql_conn.commit()
        print("MySQL cleanup successful.")
        TEACHER_DB_ID, STUDENT1_DB_ID, STUDENT2_DB_ID = None, None, None  # Clear IDs

        # MongoDB Cleanup (Exams DB)
        print("Attempting MongoDB cleanup...")
        if LOREM_IPSUM_OCR_EXAMS_ID:
            mongo_cleanup_uri = f"mongodb://{MONGO_ROOT_USER}:{MONGO_ROOT_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"
            mongo_client_cleanup = MongoClient(mongo_cleanup_uri, serverSelectionTimeoutMS=5000)

            exams_db = mongo_client_cleanup[MONGO_EXAMS_DB_NAME]
            pdf_submissions_coll = exams_db[MONGO_PDF_SUBMISSIONS_COLLECTION]
            result = pdf_submissions_coll.delete_one({"_id": ObjectId(LOREM_IPSUM_OCR_EXAMS_ID)})
            if result.deleted_count > 0:
                print(f"Deleted document from Exams DB with ID {LOREM_IPSUM_OCR_EXAMS_ID}")
            else:
                print(
                    f"Document with ID {LOREM_IPSUM_OCR_EXAMS_ID} not found in Exams DB for deletion or already deleted.")
            LOREM_IPSUM_OCR_EXAMS_ID = None  # Clear ID
        else:
            print("No MongoDB LOREM_IPSUM_OCR_EXAMS_ID to cleanup.")
        print("MongoDB cleanup (Exams DB) attempt finished.")

    except Exception as e:
        print(f"!!! Error during cleanup: {type(e).__name__} - {e} !!!")
        import traceback
        traceback.print_exc()
    finally:
        if mysql_cursor: mysql_cursor.close()
        if mysql_conn and mysql_conn.is_connected(): mysql_conn.close()
        if mongo_client_cleanup: mongo_client_cleanup.close()
    print("--- Test Data Cleanup Finished ---")


# --- Main Test Execution ---
def main():
    global TEACHER_DB_ID, STUDENT1_DB_ID, STUDENT2_DB_ID, COURSE_ID_GLOBAL, LOREM_IPSUM_OCR_EXAMS_ID

    print("======== Starting Test Script ========")
    # Wait for services
    services_to_check = [
        (USER_API_BASE_URL, "Registration Service"),
        (COURSE_API_BASE_URL, "Course Allocation Service"),
        (OLLAMA_API_BASE_URL, "Ollama AI Service", {"is_ollama": True, "timeout": 600}),
        (GRADING_API_BASE_URL, "Grading Service"),
        (PDF_PROCESSOR_API_BASE_URL, "PDF Processor Service")
    ]
    all_services_ready = True
    for url, name, *args in services_to_check:
        kwargs = args[0] if args else {}
        if not wait_for_service(url, name, **kwargs):
            all_services_ready = False
            break
    if not all_services_ready:
        print("\n!!! One or more services failed to start. Aborting tests. !!!")
        sys.exit(1)

    print("\n=== All API services ready. Starting Test Execution ===")

    try:
        print("\n=== Step 1: Register Users ===")
        teacher_payload = {"username": TEACHER_USERNAME, "password": "pw", "name": "Dr. Dyn Teach",
                           "user_type": "teacher"}
        student1_payload = {"username": STUDENT1_USERNAME, "password": "pw", "name": "Student Dyn Alpha",
                            "user_type": "student"}
        student2_payload = {"username": STUDENT2_USERNAME, "password": "pw", "name": "Student Dyn Beta",
                            "user_type": "student"}

        make_api_request("post", f"{USER_API_BASE_URL}/register", teacher_payload, description="Register Teacher")
        TEACHER_DB_ID = get_user_id_by_username(TEACHER_USERNAME)
        if not TEACHER_DB_ID: raise ValueError(f"Failed to get DB ID for teacher {TEACHER_USERNAME}")

        make_api_request("post", f"{USER_API_BASE_URL}/register", student1_payload, description="Register Student 1")
        STUDENT1_DB_ID = get_user_id_by_username(STUDENT1_USERNAME)
        if not STUDENT1_DB_ID: raise ValueError(f"Failed to get DB ID for student {STUDENT1_USERNAME}")

        make_api_request("post", f"{USER_API_BASE_URL}/register", student2_payload, description="Register Student 2")
        STUDENT2_DB_ID = get_user_id_by_username(STUDENT2_USERNAME)
        if not STUDENT2_DB_ID: raise ValueError(f"Failed to get DB ID for student {STUDENT2_USERNAME}")

        print(f"Fetched IDs -> Teacher: {TEACHER_DB_ID}, Student1: {STUDENT1_DB_ID}, Student2: {STUDENT2_DB_ID}")

        print("\n=== Step 2: Create Course ===")
        course_payload = {"name": "Dynamic Test Course Alpha", "duration_weeks": 10, "teacher_id": TEACHER_DB_ID}
        resp_course = make_api_request("post", f"{COURSE_API_BASE_URL}/courses", course_payload,
                                       description="Create Course")
        COURSE_ID_GLOBAL = resp_course.json().get('course_id')
        if not COURSE_ID_GLOBAL: raise ValueError("Course ID not returned from creation.")
        print(f"Course '{course_payload['name']}' created with ID: {COURSE_ID_GLOBAL}")

        print("\n=== Step 3: Assign Students to Course ===")
        assignment_payload = {"student_ids": [STUDENT1_DB_ID, STUDENT2_DB_ID]}
        make_api_request("put", f"{COURSE_API_BASE_URL}/courses/{COURSE_ID_GLOBAL}/students", assignment_payload,
                         description="Assign Students")

        print("\n=== Step 4: Process a test PDF via CLI (simulates student submission OCR prep) ===")
        LOREM_IPSUM_OCR_EXAMS_ID = run_docker_exec_pdf_processor_cli(
            PDF_PROCESSOR_CONTAINER_NAME,
            "pdfs/Lorem_ipsum_OCR_Version.pdf",
            username=STUDENT1_USERNAME,
            course="Dynamic Test Course Alpha",
            student_name="Student Dyn Alpha",
            student_id=STUDENT1_DB_ID,
            teacher_username=TEACHER_USERNAME,
            category="answer_sheet"
        )
        if not LOREM_IPSUM_OCR_EXAMS_ID:
            raise ValueError("Failed to process Lorem Ipsum PDF via CLI and get its Exams DB ID.")
        print(f"Lorem Ipsum PDF processed into Exams DB, ID: {LOREM_IPSUM_OCR_EXAMS_ID}")

        print("\n=== Step 5: Test Ollama AI Service (Basic Prompt) ===")
        ollama_payload = {"model": OLLAMA_TEST_MODEL, "prompt": "What is the capital of France? Respond concisely.",
                          "stream": False}
        resp_ollama = make_api_request("post", f"{OLLAMA_API_BASE_URL}/api/generate", data=ollama_payload, timeout=180,
                                       description="Ollama Generate")
        assert "paris" in resp_ollama.json().get("response",
                                                 "").lower(), "Ollama did not respond as expected about Paris"
        print("Ollama basic prompt test successful.")

        print("\n=== Step 6: Test Grading Service ===")
        grading_payload = {"document_id": LOREM_IPSUM_OCR_EXAMS_ID}
        resp_grading = make_api_request("post", f"{GRADING_API_BASE_URL}/grade_document", data=grading_payload,
                                        timeout=300, description="Grade Document")
        grading_json = resp_grading.json()
        assert "evaluation_result" in grading_json, "Grading response missing 'evaluation_result'"
        assert len(grading_json["evaluation_result"]) > 10, "Evaluation result seems too short"
        print("Grading service test successful. Evaluation obtained.")

        print("\n\n✅✅✅ Test Execution Finished Successfully ✅✅✅")
        print("Run python verify.py to check database state and Ollama model list.")

    except Exception as e:
        print(f"\n❌❌❌ An error occurred during test execution: {type(e).__name__} - {e} ❌❌❌")
        import traceback
        traceback.print_exc()
        print("=== Test Execution Failed ===")
        sys.exit(1)  # Exit with error so CI systems know it failed
    finally:
        cleanup_test_data()


if __name__ == "__main__":
    main()