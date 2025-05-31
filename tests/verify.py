import mysql.connector
from pymongo import MongoClient, errors as pymongo_errors
from bson import ObjectId # Should be imported if used, though not directly in this version's mongo check logic
from datetime import datetime
import json
import sys
import requests

# --- Configuration (should match test.py and docker-compose) ---
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "user"
MYSQL_PASSWORD = "password"
MYSQL_DB = "Informations"

MONGO_HOST = "localhost"
MONGO_PORT = 27017
MONGO_ROOT_USER = "root"
MONGO_ROOT_PASSWORD = "example"
MONGO_EXAMS_DB_NAME = "Exams"
MONGO_PDF_SUBMISSIONS_COLLECTION = "pdf_submissions"
MONGO_FRONTEND_DB_NAME = "grading_ai_frontend"
MONGO_FRONTEND_FILES_META_COLLECTION = "uploaded_material"

MONGO_URI = f"mongodb://{MONGO_ROOT_USER}:{MONGO_ROOT_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"

OLLAMA_API_BASE_URL = "http://localhost:11434"
OLLAMA_EXPECTED_MODEL = "granite3.2-vision:latest"

# Service URLs for health checks
REGISTRATION_API_URL = "http://localhost:5000"
COURSE_API_URL = "http://localhost:5001"
GRADING_API_URL = "http://localhost:5002"
PDF_PROCESSOR_API_URL = "http://localhost:5003"
NGINX_PROXY_URL = "http://localhost:8080"

# Expected data identifiers from test.py for verifying absence
EXPECTED_TEACHER_USERNAME = "test_teacher_dyn"
EXPECTED_STUDENT1_USERNAME = "test_student1_dyn"
EXPECTED_STUDENT2_USERNAME = "test_student2_dyn"
# EXPECTED_COURSE_NAME = "Dynamic Test Course Alpha" # Course name can be used if needed
EXPECTED_PDF_FILENAME_IN_EXAMS_DB = "Lorem_ipsum_OCR_Version.pdf"

# --- Helper Functions ---
def serialize_doc(doc):
    if isinstance(doc, dict):
        return {k: serialize_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_doc(elem) for elem in doc]
    elif isinstance(doc, ObjectId): # ObjectId itself
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    return doc

def get_user_from_db(cursor, username):
    cursor.execute("SELECT id, username, name, user_type FROM users WHERE username = %s", (username,))
    return cursor.fetchone()

# --- Verification Functions ---
def verify_mysql_data_after_cleanup():
    print("\n--- Verifying MySQL Data (Expecting Cleanup from test.py) ---")
    conn = None
    cursor = None
    passed_checks = 0
    total_checks = 3 # For the three users. Add more if verifying course absence.

    try:
        conn = mysql.connector.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
                                       database=MYSQL_DB, connection_timeout=10)
        cursor = conn.cursor(dictionary=True)
        print("[MySQL] Connection successful.")

        # Verify teacher is GONE
        teacher = get_user_from_db(cursor, EXPECTED_TEACHER_USERNAME)
        if not teacher:
            print(f"  ✅ Teacher '{EXPECTED_TEACHER_USERNAME}' correctly NOT found (cleaned up).")
            passed_checks += 1
        else:
            print(f"  ❌ FAILED: Teacher '{EXPECTED_TEACHER_USERNAME}' (ID: {teacher.get('id')}) was found but should have been cleaned up.")

        # Verify student1 is GONE
        student1 = get_user_from_db(cursor, EXPECTED_STUDENT1_USERNAME)
        if not student1:
            print(f"  ✅ Student '{EXPECTED_STUDENT1_USERNAME}' correctly NOT found (cleaned up).")
            passed_checks += 1
        else:
            print(f"  ❌ FAILED: Student '{EXPECTED_STUDENT1_USERNAME}' (ID: {student1.get('id')}) was found but should have been cleaned up.")

        # Verify student2 is GONE
        student2 = get_user_from_db(cursor, EXPECTED_STUDENT2_USERNAME)
        if not student2:
            print(f"  ✅ Student '{EXPECTED_STUDENT2_USERNAME}' correctly NOT found (cleaned up).")
            passed_checks += 1
        else:
            print(f"  ❌ FAILED: Student '{EXPECTED_STUDENT2_USERNAME}' (ID: {student2.get('id')}) was found but should have been cleaned up.")

        # Course and enrollments should also be gone if users are gone and cleanup was correct.
        # A more robust check would query for the course by name if its ID isn't available.
        # If test.py clears COURSE_ID_GLOBAL, we can't use it here.
        # Let's assume for now that if users are gone, related FK-constrained data is also gone.

        print(f"\n--- MySQL Verification (After Cleanup) Summary: {passed_checks}/{total_checks} checks passed ---")
        return passed_checks == total_checks
    except mysql.connector.Error as err:
        print(f"!!! MySQL Error: {err} !!!")
        return False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def verify_mongodb_data_after_cleanup():
    print("\n--- Verifying MongoDB Data (Expecting Cleanup from test.py) ---")
    client = None
    passed_checks = 0
    total_checks = 1 # For the specific OCR'd PDF
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("[MongoDB] Connection successful.")

        db_exams = client[MONGO_EXAMS_DB_NAME]
        coll_exams_submissions = db_exams[MONGO_PDF_SUBMISSIONS_COLLECTION]

        ocr_doc = coll_exams_submissions.find_one({
            "original_pdf_filename": EXPECTED_PDF_FILENAME_IN_EXAMS_DB,
            "uploader_username": EXPECTED_STUDENT1_USERNAME # Key identifier from test.py
        })
        if not ocr_doc:
            print(f"  ✅ OCR'd document for '{EXPECTED_PDF_FILENAME_IN_EXAMS_DB}' by '{EXPECTED_STUDENT1_USERNAME}' correctly NOT found (cleaned up).")
            passed_checks += 1
        else:
            print(f"  ❌ FAILED: OCR'd document for '{EXPECTED_PDF_FILENAME_IN_EXAMS_DB}' by '{EXPECTED_STUDENT1_USERNAME}' was found (ID: {ocr_doc.get('_id')}) but should have been cleaned up.")

        # Info about other collections (no specific test data expected here after cleanup)
        db_frontend = client[MONGO_FRONTEND_DB_NAME]
        coll_frontend_meta = db_frontend[MONGO_FRONTEND_FILES_META_COLLECTION]
        frontend_meta_count = coll_frontend_meta.count_documents({})
        print(f"  ℹ️  Frontend metadata collection ('{MONGO_FRONTEND_FILES_META_COLLECTION}') has {frontend_meta_count} documents (informational).")


        print(f"\n--- MongoDB Verification (After Cleanup) Summary: {passed_checks}/{total_checks} checks passed ---")
        return passed_checks == total_checks

    except pymongo_errors.ConnectionFailure as e:
        print(f"!!! MongoDB Connection Error: {e} !!!"); return False
    except Exception as e:
        print(f"!!! MongoDB verification error: {type(e).__name__}: {e} !!!"); return False
    finally:
        if client: client.close()


def verify_service_health(url, service_name, health_path="/health", expect_json=True):
    print(f"\n--- Verifying {service_name} Health ({url}{health_path}) ---")
    try:
        response = requests.get(f"{url}{health_path}", timeout=10)
        response.raise_for_status()
        msg_summary = response.text[:100]
        if expect_json:
            try:
                data = response.json(); msg_summary = data.get('message', str(data))
            except json.JSONDecodeError:
                print(f"  [{service_name}] FAILURE: Expected JSON from {health_path}. Body: {response.text[:200]}..."); return False
            # Handle cases where 'status' might not be in response (e.g. course_allocation has "message")
            if data.get("status") == "ok" or (service_name == "Course Allocation Service" and "healthy" in msg_summary.lower()):
                print(f"  [{service_name}] SUCCESS (JSON ok). Status: {response.status_code}, Msg: {msg_summary}"); return True
            else:
                print(f"  [{service_name}] FAILURE: JSON status not 'ok' or expected message not found. Resp: {data}"); return False
        else: # Not expecting JSON, 200 OK is enough
            print(f"  [{service_name}] SUCCESS (non-JSON). Status: {response.status_code}, Body: {msg_summary}..."); return True
    except requests.exceptions.RequestException as e:
        print(f"!!! {service_name} Health Check Failed: {e} !!!"); return False
    except Exception as e:
        print(f"!!! Error during {service_name} health check: {type(e).__name__}: {e} !!!"); return False
    # return False # Removed to ensure explicit True returns are primary


def verify_ollama_model():
    print(f"\n--- Verifying Ollama AI Service ({OLLAMA_API_BASE_URL}/api/tags) ---")
    try:
        response = requests.get(f"{OLLAMA_API_BASE_URL}/api/tags", timeout=20)
        response.raise_for_status(); data = response.json(); models = data.get("models", [])
        if not models: print("  [Ollama] No models found."); return False # No models at all is a failure
        print(f"  [Ollama] Found {len(models)} model(s):")
        model_found = any(m.get('name') == OLLAMA_EXPECTED_MODEL for m in models)
        for m_detail in models: print(f"    - {m_detail.get('name')}")
        print(f"  [Ollama] {'SUCCESS' if model_found else 'FAILURE'}: Expected model '{OLLAMA_EXPECTED_MODEL}' {'is available.' if model_found else 'NOT found.'}")
        return model_found
    except requests.exceptions.RequestException as e:
        print(f"!!! Ollama API Request Failed: {e} !!!"); return False
    except Exception as e: # Broader exception catch
        print(f"!!! Error during Ollama verification: {type(e).__name__}: {e} !!!"); return False
    # finally: # Finally without a try doesn't make sense here, removed print from it.
    #    print("--- Ollama Verification Complete ---") # This can be after the return or not at all.


# --- Main Verification Execution ---
if __name__ == "__main__":
    print("\n======== Starting Verification Script (Post Test-With-Cleanup) ========")
    results = {
        "Registration Svc Health": verify_service_health(REGISTRATION_API_URL, "Registration Service"),
        "Course Alloc Svc Health": verify_service_health(COURSE_API_URL, "Course Allocation Service"), # It does not have "status":"ok"
        "Grading Svc Health": verify_service_health(GRADING_API_URL, "Grading Service"),
        "PDF Processor Svc Health": verify_service_health(PDF_PROCESSOR_API_URL, "PDF Processor Service"),
        "Nginx Proxy Health": verify_service_health(NGINX_PROXY_URL, "Nginx Proxy", health_path="/nginx_health", expect_json=False),
        "MySQL Data (Post-Cleanup)": verify_mysql_data_after_cleanup(),
        "MongoDB Data (Post-Cleanup)": verify_mongodb_data_after_cleanup(),
        "Ollama Model": verify_ollama_model()
    }
    print("\n\n======== Verification Summary ========")
    all_passed = True
    for check_name, status in results.items():
        print(f"{check_name + ':' :<30} {'✅ SUCCESS' if status else '❌ FAILED'}")
        if not status: all_passed = False
    print("======================================")
    if not all_passed:
        print("\n❌ One or more verifications failed."); sys.exit(1)
    else:
        print("\n✅ All verifications passed successfully!"); sys.exit(0)