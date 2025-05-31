import mysql.connector
from pymongo import MongoClient, errors as pymongo_errors
from bson import ObjectId
from datetime import datetime
import json
import sys
import requests

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
MONGO_FRONTEND_FILES_COLLECTION = "uploaded_material"  # GridFS uses fs.files and fs.chunks
MONGO_URI = f"mongodb://{MONGO_ROOT_USER}:{MONGO_ROOT_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"

OLLAMA_API_BASE_URL = "http://localhost:11434"
OLLAMA_EXPECTED_MODEL = "granite3.2-vision:latest"

# Service URLs for health checks
REGISTRATION_API_URL = "http://localhost:5000"
COURSE_API_URL = "http://localhost:5001"
GRADING_API_URL = "http://localhost:5002"
PDF_PROCESSOR_API_URL = "http://localhost:5003"
NGINX_PROXY_URL = "http://localhost:8080"


def serialize_doc(doc):
    if isinstance(doc, dict):
        return {k: serialize_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_doc(elem) for elem in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    return doc


def verify_mysql():
    print("\n--- Verifying MySQL Data (DB: Informations) ---")
    conn = None;
    cursor = None
    try:
        conn = mysql.connector.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
                                       database=MYSQL_DB, connection_timeout=10)
        cursor = conn.cursor(dictionary=True)
        print("\n[MySQL] Checking 'users' table...")
        cursor.execute("SELECT id, username, name, user_type FROM users ORDER BY id;")
        users = cursor.fetchall();
        print(f"  Found {len(users)} users:" if users else "  No users found.")
        for user in users: print(f"    {user}")
        print("\n[MySQL] Checking 'courses' table...")
        cursor.execute("SELECT course_id, name, duration_weeks, teacher_id, is_active FROM courses ORDER BY course_id;")
        courses = cursor.fetchall();
        print(f"  Found {len(courses)} courses:" if courses else "  No courses found.")
        for course in courses: print(f"    {course}")
        print("\n[MySQL] Checking 'student_course' table (enrollments)...")
        cursor.execute("SELECT enrollment_id, student_id, course_id, grade FROM student_course ORDER BY enrollment_id;")
        assignments = cursor.fetchall();
        print(f"  Found {len(assignments)} enrollments:" if assignments else "  No enrollments.")
        for assignment in assignments: print(f"    {assignment}")
        print("\n--- MySQL Verification Complete ---");
        return True
    except mysql.connector.Error as err:
        print(f"!!! MySQL Error: {err} !!!"); return False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def verify_mongodb():
    print("\n--- Verifying MongoDB Data ---")
    client = None;
    success = True
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster');
        print("[MongoDB] Connection successful.")

        db_exams = client[MONGO_EXAMS_DB_NAME]
        coll_exams = db_exams[MONGO_PDF_SUBMISSIONS_COLLECTION]
        print(f"\n[MongoDB] Checking '{coll_exams.name}' in '{MONGO_EXAMS_DB_NAME}' DB (OCR'd submissions)...")
        exam_docs = list(coll_exams.find().sort("upload_time", -1).limit(3))
        total_exam_docs = coll_exams.count_documents({})
        print(
            f"  Found {total_exam_docs} docs. Displaying up to 3 (newest first):" if exam_docs else f"  No docs in '{coll_exams.name}'.")
        for doc in exam_docs: display_doc = {k: v for k, v in doc.items() if k != "content"}; print(
            json.dumps(serialize_doc(display_doc), indent=2)); print("-" * 20)

        db_frontend = client[MONGO_FRONTEND_DB_NAME]
        coll_frontend_meta = db_frontend[MONGO_FRONTEND_FILES_COLLECTION]
        print(
            f"\n[MongoDB] Checking '{coll_frontend_meta.name}' in '{MONGO_FRONTEND_DB_NAME}' DB (UI upload metadata)...")
        frontend_meta_docs = list(coll_frontend_meta.find().sort("upload_timestamp", -1).limit(3))
        total_frontend_meta_docs = coll_frontend_meta.count_documents({})
        print(
            f"  Found {total_frontend_meta_docs} docs. Displaying up to 3:" if frontend_meta_docs else f"  No docs in '{coll_frontend_meta.name}'.")
        for doc in frontend_meta_docs: print(json.dumps(serialize_doc(doc), indent=2)); print("-" * 20)

        coll_frontend_gridfs_files = db_frontend["fs.files"]  # GridFS files collection
        print(f"\n[MongoDB] Checking 'fs.files' in '{MONGO_FRONTEND_DB_NAME}' DB (GridFS actual files)...")
        gridfs_files_docs = list(coll_frontend_gridfs_files.find().sort("uploadDate", -1).limit(3))
        total_gridfs_files = coll_frontend_gridfs_files.count_documents({})
        print(
            f"  Found {total_gridfs_files} GridFS files. Displaying metadata for up to 3:" if gridfs_files_docs else "  No GridFS files found.")
        for doc in gridfs_files_docs: print(json.dumps(serialize_doc(doc), indent=2)); print("-" * 20)

    except pymongo_errors.ConnectionFailure as e:
        print(f"!!! MongoDB Connection Error: {e} !!!"); success = False
    except pymongo_errors.OperationFailure as e:
        print(f"!!! MongoDB Operation Error: {e} !!!"); success = False
    except Exception as e:
        print(f"!!! MongoDB verification error: {type(e).__name__}: {e} !!!"); success = False
    finally:
        if client: client.close()
    print("\n--- MongoDB Verification Complete ---");
    return success


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
                print(
                    f"  [{service_name}] FAILURE: Expected JSON from {health_path}. Body: {response.text[:200]}..."); return False
            if data.get("status") == "ok":
                print(
                    f"  [{service_name}] SUCCESS (JSON ok). Status: {response.status_code}, Msg: {msg_summary}"); return True
            else:
                print(f"  [{service_name}] FAILURE: JSON status not 'ok'. Resp: {data}"); return False
        else:  # Not expecting JSON, 200 OK is enough
            print(f"  [{service_name}] SUCCESS (non-JSON). Status: {response.status_code}, Body: {msg_summary}...");
            return True
    except requests.exceptions.RequestException as e:
        print(f"!!! {service_name} Health Check Failed: {e} !!!"); return False
    except Exception as e:
        print(f"!!! Error during {service_name} health check: {type(e).__name__}: {e} !!!"); return False


def verify_ollama_model():
    print(f"\n--- Verifying Ollama AI Service ({OLLAMA_API_BASE_URL}/api/tags) ---")
    try:
        response = requests.get(f"{OLLAMA_API_BASE_URL}/api/tags", timeout=20)
        response.raise_for_status();
        data = response.json();
        models = data.get("models", [])
        if not models: print("  [Ollama] No models found."); return False
        print(f"  [Ollama] Found {len(models)} model(s):")
        model_found = any(m.get('name') == OLLAMA_EXPECTED_MODEL for m in models)
        for m_detail in models: print(f"    - {m_detail.get('name')}")
        print(
            f"  [Ollama] {'SUCCESS' if model_found else 'FAILURE'}: Expected model '{OLLAMA_EXPECTED_MODEL}' {'is available' if model_found else 'NOT found'}.")
        return model_found
    except requests.exceptions.RequestException as e:
        print(f"!!! Ollama API Request Failed: {e} !!!"); return False
    except Exception as e:
        print(f"!!! Error during Ollama verification: {type(e).__name__}: {e} !!!"); return False
    finally:
        print("--- Ollama Verification Complete ---")


if __name__ == "__main__":
    print("\n======== Starting Verification Script ========")
    results = {
        "Registration Svc Health": verify_service_health(REGISTRATION_API_URL, "Registration Service"),
        "Course Alloc Svc Health": verify_service_health(COURSE_API_URL, "Course Allocation Service"),
        "Grading Svc Health": verify_service_health(GRADING_API_URL, "Grading Service"),
        "PDF Processor Svc Health": verify_service_health(PDF_PROCESSOR_API_URL, "PDF Processor Service"),
        "Nginx Proxy Health": verify_service_health(NGINX_PROXY_URL, "Nginx Proxy", health_path="/nginx_health",
                                                    expect_json=False),
        "MySQL Data": verify_mysql(),
        "MongoDB Data": verify_mongodb(),
        "Ollama Model": verify_ollama_model()
    }
    print("\n\n======== Verification Summary ========")
    all_passed = True
    for check_name, status in results.items():
        print(f"{check_name + ':' :<30} {'SUCCESS' if status else 'FAILED'}")
        if not status: all_passed = False
    print("======================================")
    if not all_passed:
        print("\nOne or more verifications failed."); sys.exit(1)
    else:
        print("\nAll verifications passed successfully!"); sys.exit(0)