import mysql.connector
from pymongo import MongoClient
import json
import sys
import requests

# --- Configuration ---
MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB = "localhost", 3306, "user", "password", "Informations"
MONGO_HOST, MONGO_PORT, MONGO_ROOT_USER, MONGO_ROOT_PASSWORD, MONGO_EXAMS_DB_NAME = "localhost", 27017, "root", "example", "Exams"
MONGO_URI = f"mongodb://{MONGO_ROOT_USER}:{MONGO_ROOT_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"
SEEDBOX_API_PUBLIC_URL = "https://api.seedbox.ai"
REGISTRATION_API_URL, COURSE_API_URL, GRADING_API_URL, PDF_PROCESSOR_API_URL, NGINX_PROXY_URL = "http://localhost:5000", "http://localhost:5001", "http://localhost:5002", "http://localhost:5003", "http://localhost:8080"
EXPECTED_TEACHER_USERNAME, EXPECTED_STUDENT1_USERNAME, EXPECTED_PDF_FILENAME = "test_teacher_dyn", "test_student1_dyn", "Lorem_ipsum_OCR_Version.pdf"


# --- Verification Functions ---
def verify_service_health(url, name, health_path="/health", expect_json=True):
    # This function remains the same
    print(f"\n--- Verifying {name} Health ({url}{health_path}) ---")
    try:
        response = requests.get(f"{url}{health_path}", timeout=10)
        response.raise_for_status()
        if expect_json:
            data = response.json()
            if data.get("status") == "ok" or "healthy" in data.get("message", "").lower():
                print(f"  ✅ SUCCESS: {name} is healthy.")
                return True
        else:
            print(f"  ✅ SUCCESS: {name} is healthy.")
            return True
        print(f"  ❌ FAILED: {name} health check response not as expected.")
        return False
    except Exception as e:
        print(f"!!! {name} Health Check Failed: {e} !!!")
        return False


def verify_data_after_cleanup():
    # This function combines DB checks for post-cleanup state
    print("\n--- Verifying Data State (Expecting Cleanup from test.py) ---")
    passed = True
    try:  # MySQL Check
        conn = mysql.connector.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (EXPECTED_TEACHER_USERNAME,))
        if cursor.fetchone()[0] == 0:
            print("  ✅ MySQL: Test users correctly NOT found.")
        else:
            print("  ❌ FAILED: MySQL: Test users found but should be cleaned up.")
            passed = False
        conn.close()
    except Exception as e:
        print(f"!!! MySQL verification error: {e} !!!");
        passed = False

    try:  # MongoDB Check
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        count = client[MONGO_EXAMS_DB_NAME]["pdf_submissions"].count_documents(
            {"original_pdf_filename": EXPECTED_PDF_FILENAME, "uploader_username": EXPECTED_STUDENT1_USERNAME})
        if count == 0:
            print("  ✅ MongoDB: Test document correctly NOT found.")
        else:
            print("  ❌ FAILED: MongoDB: Test document found but should be cleaned up.")
            passed = False
        client.close()
    except Exception as e:
        print(f"!!! MongoDB verification error: {e} !!!");
        passed = False
    return passed


def verify_seedbox_connectivity():
    print(f"\n--- Verifying Seedbox AI Connectivity ({SEEDBOX_API_PUBLIC_URL}/models) ---")
    try:
        response = requests.get(f"{SEEDBOX_API_PUBLIC_URL}/models", timeout=20)
        response.raise_for_status()
        if response.json().get("chat_models"):
            print(f"  ✅ SUCCESS: Connected to Seedbox API and found chat models.")
            return True
        print("  ❌ FAILED: Connected, but no chat models listed.")
        return False
    except Exception as e:
        print(f"!!! Seedbox API Connectivity Check Failed: {e} !!!")
        return False


# --- Main Verification Execution ---
if __name__ == "__main__":
    print("\n======== Starting Verification Script ========")
    results = {
        "Registration Svc Health": verify_service_health(REGISTRATION_API_URL, "Registration Service"),
        "Course Alloc Svc Health": verify_service_health(COURSE_API_URL, "Course Allocation Service"),
        "Grading Svc Health": verify_service_health(GRADING_API_URL, "Grading Service"),
        "PDF Processor Svc Health": verify_service_health(PDF_PROCESSOR_API_URL, "PDF Processor Service"),
        "Nginx Proxy Health": verify_service_health(NGINX_PROXY_URL, "Nginx Proxy", health_path="/nginx_health",
                                                    expect_json=False),
        "Data State (Post-Cleanup)": verify_data_after_cleanup(),
        "Seedbox API Connectivity": verify_seedbox_connectivity()
    }
    all_passed = all(results.values())
    print("\n\n======== Verification Summary ========")
    for name, status in results.items():
        print(f"{name + ':' :<30} {'✅ SUCCESS' if status else '❌ FAILED'}")
    if all_passed:
        print("\n✅ All verifications passed successfully!");
        sys.exit(0)
    else:
        print("\n❌ One or more verifications failed.");
        sys.exit(1)