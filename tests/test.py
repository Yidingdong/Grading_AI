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
PDF_PROCESSOR_API_BASE_URL = "http://localhost:5003"  # New service for OCR processing
PDF_UPLOADER_CONTAINER_NAME = "pdf-processor-app"  # Updated container name

OLLAMA_TEST_MODEL = "granite3.2-vision:latest"
LOREM_IPSUM_GRIDFS_ID_FRONTEND = None  # For student UI upload
LOREM_IPSUM_OCR_EXAMS_ID = None  # For result in Exams DB

TEACHER_DB_ID = None
STUDENT1_DB_ID = None
STUDENT2_DB_ID = None


def wait_for_service(url, service_name, timeout=120, health_path="/health", is_ollama=False):
    # ... (function as before, no critical changes needed here for this sync)
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
                        models_data = response.json()
                        if any(m.get("name") == OLLAMA_TEST_MODEL for m in models_data.get("models", [])):
                            print(f"\n{service_name} is up and model '{OLLAMA_TEST_MODEL}' is available.")
                            return True
                        else:
                            print(
                                f".(Ollama up, model {OLLAMA_TEST_MODEL} not yet listed: {models_data.get('models', [])})",
                                end='', flush=True)
                    except json.JSONDecodeError:
                        print(f".(Ollama up, but {check_url} response not JSON: {response.text[:100]})", end='',
                              flush=True)
                else:
                    print(f".(Ollama status {response.status_code} from {check_url})", end='', flush=True)
            elif response.status_code == 200:
                print(f"\n{service_name} responded with status {response.status_code} from {check_url}. Ready.")
                return True
            else:
                print(f".(status {response.status_code} from {check_url})", end='', flush=True)
        except requests.exceptions.ConnectionError:
            print(".", end='', flush=True)
        except requests.exceptions.Timeout:
            print("T", end='', flush=True)
        except requests.exceptions.RequestException as e:
            print(f"\nError checking {service_name} @ {check_url}: {e}")
        time.sleep(5)
    print(f"\nError: Timeout waiting for {service_name} at {url} after {timeout} seconds.")
    return False


def run_docker_exec_pdf_processor_cli(container_name, pdf_path_in_container, username, course, student_name, student_id,
                                      teacher, category, lang="eng", ocr_dpi=300):
    """ Helper to run the original CLI-style pdf_to_mongodb.py for setup if needed """
    # This is kept if direct CLI processing is still part of some test setup
    # but new tests might prefer calling the PDF Processor API.
    command_args = [
        "python", "pdf_to_mongodb.py",  # Assuming pdf_to_mongodb.py is still the entry point for CLI mode in that image
        "--pdf", pdf_path_in_container,
        "--username", username, "--course", course,
        "--student-name", student_name,
        "--teacher", teacher, "--category", category, "--lang", lang,
        "--ocr-dpi", str(ocr_dpi)
    ]
    if student_id:  # student_id is optional for some categories
        command_args.extend(["--student-id", str(student_id)])

    base_command = ["docker", "exec", container_name]
    full_command = base_command + command_args
    print(f"\n--- Running Docker Exec (CLI PDF Processing) ---")
    print(f"Command: {' '.join(shlex.quote(str(arg)) for arg in full_command)}")
    try:
        result = subprocess.run(full_command, capture_output=True, text=True, check=True, encoding='utf-8')
        print("--- Docker Exec Output ---")
        if result.stdout: print("STDOUT:\n", result.stdout.strip())
        if result.stderr: print("STDERR:\n", result.stderr.strip())  # pdf_to_mongodb.py logs to stderr
        print("--- Docker Exec End ---")
        # Parse ID from output (assuming it's in stderr now due to logging)
        output_to_search = result.stdout + "\n" + result.stderr
        match = re.search(r"Submission ID: ([0-9a-fA-F]+)", output_to_search)
        if match: return match.group(1)
        return None
    except subprocess.CalledProcessError as e:
        print(f"!!! Docker exec CLI PDF processing failed (exit code {e.returncode}) !!!")
        if e.stdout: print("STDOUT:\n", e.stdout.strip())
        if e.stderr: print("STDERR:\n", e.stderr.strip())
        raise
    return None


def make_api_request(method, url, data=None, headers=None, timeout=30, description="API Request"):
    # ... (function as before, no critical changes needed here for this sync)
    print(f"\n--- Making {description} ---")
    print(f"Method: {method.upper()}, URL: {url}")
    if data: print(f"Data: {json.dumps(data)}")
    if headers is None:
        headers = {'Content-Type': 'application/json'}
    elif data and 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json'
    try:
        response = requests.request(method, url, json=data if method.lower() != 'get' else None,
                                    params=data if method.lower() == 'get' else None, headers=headers, timeout=timeout)
        response_body_text = "N/A";
        response_body_json = None
        try:
            response_body_json = response.json(); response_body_text = json.dumps(response_body_json)
        except json.JSONDecodeError:
            response_body_text = response.text
        print(f"Response Status: {response.status_code}, Body: {response_body_text[:500]}...")  # Limit long responses
        response.raise_for_status()
        print(f"--- {description} End ---")
        return response
    except requests.exceptions.HTTPError as e:
        print(f"!!! {description} HTTP Error: {e} !!!"); raise
    except requests.exceptions.RequestException as e:
        print(f"!!! {description} Failed: {e} !!!"); raise


print("======== Starting Test Script ========")
# Wait for services
services_to_check = [
    (USER_API_BASE_URL, "Registration Service"),
    (COURSE_API_BASE_URL, "Course Allocation Service"),
    (OLLAMA_API_BASE_URL, "Ollama AI Service", {"is_ollama": True, "timeout": 600}),
    (GRADING_API_BASE_URL, "Grading Service"),
    (PDF_PROCESSOR_API_BASE_URL, "PDF Processor Service")  # New service
]
all_services_ready = True
for url, name, *args in services_to_check:
    kwargs = args[0] if args else {}
    if not wait_for_service(url, name, **kwargs):
        all_services_ready = False;
        break
if not all_services_ready:
    print("\n!!! One or more services failed to start. Aborting tests. !!!");
    sys.exit(1)

print("\n=== All API services ready. Starting Test Execution ===")
try:
    print("\n=== Step 1: Register Users ===")
    teacher_payload = {"username": "test_teacher1", "password": "pw", "name": "Dr. Teach", "user_type": "teacher"}
    student1_payload = {"username": "test_student1", "password": "pw", "name": "Student Alpha", "user_type": "student"}
    student2_payload = {"username": "test_student2", "password": "pw", "name": "Student Beta", "user_type": "student"}

    # Robust ID handling: Store actual IDs if API returns them or query DB. For now, assume sequential or specific test DB state.
    # To ensure clean state for IDs, tests should ideally clear users table first.
    # Here, we'll assume IDs are 1, 2, 3 if it's a fresh DB.
    resp_teacher = make_api_request("post", f"{USER_API_BASE_URL}/register", teacher_payload,
                                    description="Register Teacher")
    # Assuming register API doesn't return ID, so we can't reliably get TEACHER_DB_ID here without DB query.
    # For tests, it's better if APIs return created resource IDs.
    # For now, we'll proceed with hardcoded assumptions or skip tests that depend on exact IDs if they become flaky.
    TEACHER_DB_ID = 1  # This is a MAJOR assumption for the test flow.
    STUDENT1_DB_ID = 2
    STUDENT2_DB_ID = 3
    make_api_request("post", f"{USER_API_BASE_URL}/register", student1_payload, description="Register Student 1")
    make_api_request("post", f"{USER_API_BASE_URL}/register", student2_payload, description="Register Student 2")

    print(f"Assuming Teacher ID: {TEACHER_DB_ID}, Student1 ID: {STUDENT1_DB_ID}, Student2 ID: {STUDENT2_DB_ID}")

    print("\n=== Step 2: Create Course ===")
    course_payload = {"name": "Test Course Alpha", "duration_weeks": 10,
                      "teacher_id": TEACHER_DB_ID}  # Assumes TEACHER_DB_ID is correct
    resp_course = make_api_request("post", f"{COURSE_API_BASE_URL}/courses", course_payload,
                                   description="Create Course")
    course_id = resp_course.json().get('course_id')
    if not course_id: raise ValueError("Course ID not returned from creation.")
    print(f"Course '{course_payload['name']}' created with ID: {course_id}")

    print("\n=== Step 3: Assign Students to Course ===")
    assignment_payload = {"student_ids": [STUDENT1_DB_ID, STUDENT2_DB_ID]}  # Assumes these IDs are correct
    make_api_request("put", f"{COURSE_API_BASE_URL}/courses/{course_id}/students", assignment_payload,
                     description="Assign Students")

    # Step 4 & 5 are now about simulating student UI upload and then teacher processing
    # We can't easily simulate UI upload to GridFS via test.py without frontend interaction or a new file upload API in frontend.
    # So, we'll use the pdf-processor CLI mode for one file to get it into Exams.pdf_submissions for AI grading test.
    print("\n=== Step 4: Process a test PDF (simulating it was uploaded by student and needs OCR) ===")
    # This step now uses the CLI mode of pdf_to_mongodb.py for simplicity to get a doc into Exams DB
    # In a real scenario, this would be student uploading to GridFS via UI, then teacher triggering OCR via API.
    LOREM_IPSUM_OCR_EXAMS_ID = run_docker_exec_pdf_processor_cli(
        PDF_UPLOADER_CONTAINER_NAME,
        "/app/pdfs/Lorem_ipsum_OCR_Version.pdf",  # Path inside pdf-processor container
        username="test_student1",  # Uploader
        course="Test Course Alpha",
        student_name="Student Alpha",
        student_id=STUDENT1_DB_ID,  # Actual student ID
        teacher="Dr. Teach",  # Teacher's username
        category="answer_sheet"
    )
    if not LOREM_IPSUM_OCR_EXAMS_ID:
        raise ValueError("Failed to process Lorem Ipsum PDF and get its Exams DB ID.")
    print(f"Lorem Ipsum PDF processed into Exams DB, ID: {LOREM_IPSUM_OCR_EXAMS_ID}")

    # Step 5: Test Ollama (remains the same)
    print("\n=== Step 5: Test Ollama AI Service ===")  # Renumbered
    ollama_payload = {"model": OLLAMA_TEST_MODEL, "prompt": "What is the capital of France?", "stream": False}
    make_api_request("post", f"{OLLAMA_API_BASE_URL}/api/generate", data=ollama_payload, timeout=120,
                     description="Ollama Generate")

    # Step 6: Test Grading Service using the OCR'd document ID
    print("\n=== Step 6: Test Grading Service ===")  # Renumbered
    if LOREM_IPSUM_OCR_EXAMS_ID:
        grading_payload = {"document_id": LOREM_IPSUM_OCR_EXAMS_ID}
        make_api_request("post", f"{GRADING_API_BASE_URL}/grade_document", data=grading_payload, timeout=240,
                         description="Grade Document")
    else:
        print("Skipping Grading Service test as LOREM_IPSUM_OCR_EXAMS_ID was not captured.")

    print("\n=== Test Execution Finished Successfully ===")
    print("=== Run python verify.py to check database state and Ollama model list ===")

except Exception as e:
    print(f"\n!!! An error occurred during test execution: {type(e).__name__} - {e} !!!")
    import traceback

    traceback.print_exc()
    print("=== Test Execution Failed ===");
    sys.exit(1)