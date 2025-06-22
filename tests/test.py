import requests
import subprocess
import json
import shlex
import time
import sys
import re
import mysql.connector
from pymongo import MongoClient
from bson import ObjectId

# --- Configuration ---
USER_API_BASE_URL = "http://localhost:5000"
COURSE_API_BASE_URL = "http://localhost:5001"
GRADING_API_BASE_URL = "http://localhost:5002"
PDF_PROCESSOR_API_BASE_URL = "http://localhost:5003"
PDF_PROCESSOR_CONTAINER_NAME = "pdf-processor-app"

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
def wait_for_service(url, service_name, timeout=180, health_path="/health"):
    print(f"Waiting for {service_name} at {url} (timeout: {timeout}s)...")
    start_time = time.time()
    check_url = f"{url}{health_path}"

    while time.time() - start_time < timeout:
        try:
            response = requests.get(check_url, timeout=10)
            if response.status_code == 200:
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
    # This function was simplified in your logs, so I'll match that
    print(f"\n--- Making {description} ---")
    print(f"Method: {method.upper()}, URL: {url}")
    if data: print(f"Data: {json.dumps(data)}")

    try:
        response = requests.request(method, url, json=data, headers={'Content-Type': 'application/json'},
                                    timeout=timeout)
        response_text = "N/A"
        if response.content:
            try:
                response_text = json.dumps(response.json())
            except json.JSONDecodeError:
                response_text = response.text
        print(f"Response Status: {response.status_code}, Body: {response_text[:500]}...")
        response.raise_for_status()
        print(f"--- {description} Successful ---")
        return response
    except requests.exceptions.HTTPError as e:
        print(f"!!! {description} HTTP Error: {e} !!!")
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
            return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def run_docker_exec_pdf_processor_cli(container_name, pdf_path_in_container, username, course, course_id, student_name,
                                      student_id,
                                      teacher_username, category, lang="eng"):
    command_args = [
        "python", "pdf_to_mongodb.py", "--pdf", pdf_path_in_container,
        "--username", username, "--course", course, "--course-id", str(course_id),
        "--student-name", student_name, "--teacher", teacher_username,
        "--category", category, "--lang", lang
    ]
    if student_id:
        command_args.extend(["--student-id", str(student_id)])

    full_command = ["docker", "exec", container_name] + command_args
    print(f"\n--- Running Docker Exec (CLI PDF Processing for Setup) ---")
    print(f"Command: {' '.join(shlex.quote(str(arg)) for arg in full_command)}")
    try:
        result = subprocess.run(full_command, capture_output=True, text=True, check=False, encoding='utf-8')
        output_to_search = result.stdout + "\n" + result.stderr
        print("--- Docker Exec Output ---")
        print("STDOUT:\n", result.stdout.strip() if result.stdout else " (empty)")
        print("STDERR:\n", result.stderr.strip() if result.stderr else " (empty)")
        print("--- Docker Exec End ---")

        match_id = re.search(r"Submission ID: ([0-9a-fA-F]{24})", output_to_search)
        if match_id:
            print(f"Found Submission ID from CLI output: {match_id.group(1)}")
            return match_id.group(1)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, full_command, output=result.stdout,
                                                stderr=result.stderr)

        return None
    except Exception as e:
        print(f"!!! Unexpected error during Docker exec: {e} !!!")
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
        if COURSE_ID_GLOBAL:
            mysql_cursor.execute("DELETE FROM student_course WHERE course_id = %s", (COURSE_ID_GLOBAL,))
            print(f"Deleted enrollments for course ID {COURSE_ID_GLOBAL}")
            mysql_cursor.execute("DELETE FROM courses WHERE course_id = %s", (COURSE_ID_GLOBAL,))
            print(f"Deleted course with ID {COURSE_ID_GLOBAL}")

        user_ids = [uid for uid in [TEACHER_DB_ID, STUDENT1_DB_ID, STUDENT2_DB_ID] if uid is not None]
        for user_id in user_ids:
            mysql_cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            print(f"Deleted user with ID {user_id}")
        mysql_conn.commit()
        print("MySQL cleanup successful.")

        # MongoDB Cleanup
        print("Attempting MongoDB cleanup...")
        if LOREM_IPSUM_OCR_EXAMS_ID:
            mongo_uri = f"mongodb://{MONGO_ROOT_USER}:{MONGO_ROOT_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"
            mongo_client_cleanup = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            exams_db = mongo_client_cleanup[MONGO_EXAMS_DB_NAME]
            result = exams_db[MONGO_PDF_SUBMISSIONS_COLLECTION].delete_one({"_id": ObjectId(LOREM_IPSUM_OCR_EXAMS_ID)})
            if result.deleted_count > 0:
                print(f"Deleted document from Exams DB with ID {LOREM_IPSUM_OCR_EXAMS_ID}")
        else:
            print("No MongoDB document ID to cleanup.")
        print("MongoDB cleanup attempt finished.")

    except Exception as e:
        print(f"!!! Error during cleanup: {e} !!!")
        import traceback
        traceback.print_exc()
    finally:
        TEACHER_DB_ID, STUDENT1_DB_ID, STUDENT2_DB_ID, COURSE_ID_GLOBAL, LOREM_IPSUM_OCR_EXAMS_ID = None, None, None, None, None
        if mysql_cursor: mysql_cursor.close()
        if mysql_conn and mysql_conn.is_connected(): mysql_conn.close()
        if mongo_client_cleanup: mongo_client_cleanup.close()
    print("--- Test Data Cleanup Finished ---")


def main():
    global TEACHER_DB_ID, STUDENT1_DB_ID, STUDENT2_DB_ID, COURSE_ID_GLOBAL, LOREM_IPSUM_OCR_EXAMS_ID

    print("======== Starting Test Script ========")
    services_to_check = [
        (USER_API_BASE_URL, "Registration Service"),
        (COURSE_API_BASE_URL, "Course Allocation Service"),
        (GRADING_API_BASE_URL, "Grading Service"),
        (PDF_PROCESSOR_API_BASE_URL, "PDF Processor Service")
    ]
    for url, name in services_to_check:
        if not wait_for_service(url, name):
            sys.exit(f"Service {name} failed to start. Aborting tests.")

    print("\n=== All API services ready. Starting Test Execution ===")

    try:
        print("\n=== Step 1: Register Users ===")
        teacher_payload = {"username": TEACHER_USERNAME, "password": "pw", "name": "Dr. Dyn Teach",
                           "user_type": "teacher"}
        resp = make_api_request("post", f"{USER_API_BASE_URL}/register", teacher_payload,
                                description="Register Teacher")
        TEACHER_DB_ID = get_user_id_by_username(TEACHER_USERNAME)

        student1_payload = {"username": STUDENT1_USERNAME, "password": "pw", "name": "Student Dyn Alpha",
                            "user_type": "student"}
        resp = make_api_request("post", f"{USER_API_BASE_URL}/register", student1_payload,
                                description="Register Student 1")
        STUDENT1_DB_ID = get_user_id_by_username(STUDENT1_USERNAME)

        student2_payload = {"username": STUDENT2_USERNAME, "password": "pw", "name": "Student Dyn Beta",
                            "user_type": "student"}
        resp = make_api_request("post", f"{USER_API_BASE_URL}/register", student2_payload,
                                description="Register Student 2")
        STUDENT2_DB_ID = get_user_id_by_username(STUDENT2_USERNAME)

        print("\n=== Step 2: Create Course ===")
        course_payload = {"name": "Dynamic Test Course Alpha", "duration_weeks": 10, "teacher_id": TEACHER_DB_ID}
        resp = make_api_request("post", f"{COURSE_API_BASE_URL}/courses", course_payload, description="Create Course")
        COURSE_ID_GLOBAL = resp.json()['course_id']

        print("\n=== Step 3: Assign Students to Course ===")
        assignment_payload = {"student_ids": [STUDENT1_DB_ID, STUDENT2_DB_ID]}
        make_api_request("put", f"{COURSE_API_BASE_URL}/courses/{COURSE_ID_GLOBAL}/students", assignment_payload,
                         description="Assign Students")

        print("\n=== Step 4: Process a test PDF via CLI (simulates student submission) ===")
        LOREM_IPSUM_OCR_EXAMS_ID = run_docker_exec_pdf_processor_cli(
            PDF_PROCESSOR_CONTAINER_NAME, "pdfs/Lorem_ipsum_OCR_Version.pdf",
            username=STUDENT1_USERNAME, course="Dynamic Test Course Alpha", course_id=COURSE_ID_GLOBAL,
            student_name="Student Dyn Alpha", student_id=STUDENT1_DB_ID,
            teacher_username=TEACHER_USERNAME, category="answer_sheet"
        )

        print("\n=== Step 5: Test Grading Service (Main AI Integration Test) ===")
        grading_payload = {"document_id": LOREM_IPSUM_OCR_EXAMS_ID}
        resp = make_api_request("post", f"{GRADING_API_BASE_URL}/grade_document", grading_payload, timeout=120,
                                description="Grade Document")
        assert "evaluation_result" in resp.json(), "Response missing evaluation"
        assert "Overall Grade:" in resp.json()["evaluation_result"], "Evaluation missing 'Overall Grade:'"

        print("\n✅✅✅ Test Execution Finished Successfully ✅✅✅")

    except Exception as e:
        print(f"\n❌❌❌ An error occurred: {e} ❌❌❌")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cleanup_test_data()


if __name__ == "__main__":
    main()