import mysql.connector
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import json
from bson import ObjectId
from datetime import datetime
import sys
import requests

MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "user"
MYSQL_PASSWORD = "password"
MYSQL_DB = "Informations"

MONGO_HOST = "localhost"
MONGO_PORT = 27017
MONGO_USER = "root"
MONGO_PASSWORD = "example"
MONGO_DB_NAME = "Exams"
MONGO_COLLECTION = "pdf_submissions"
MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"

OLLAMA_API_BASE_URL = "http://localhost:11434"
OLLAMA_EXPECTED_MODEL = "granite3.2-vision:latest"
GRADING_API_BASE_URL = "http://localhost:5002"  # <-- NEW


def serialize_doc(doc):
    if isinstance(doc, dict):
        return {k: serialize_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_doc(elem) for elem in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    else:
        return doc


def verify_mysql():
    print("--- Verifying MySQL Data ---")
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB
        )
        cursor = conn.cursor(dictionary=True)

        print("\n[MySQL] Checking 'users' table...")
        cursor.execute("SELECT id, username, name, user_type FROM users;")
        users = cursor.fetchall()
        if users:
            print(f"  Found {len(users)} users:")
            for user in users:
                print(f"    {user}")
        else:
            print("  No users found.")

        print("\n[MySQL] Checking 'courses' table...")
        cursor.execute("SELECT course_id, name, duration_weeks, teacher_id FROM courses;")
        courses = cursor.fetchall()
        if courses:
            print(f"  Found {len(courses)} courses:")
            for course in courses:
                print(f"    {course}")
        else:
            print("  No courses found.")

        print("\n[MySQL] Checking 'student_course' table (assignments)...")
        cursor.execute("SELECT student_id, course_id FROM student_course;")
        assignments = cursor.fetchall()
        if assignments:
            print(f"  Found {len(assignments)} student assignments:")
            for assignment in assignments:
                print(f"    {assignment}")
        else:
            print("  No student assignments found.")

        print("\n--- MySQL Verification Complete ---")
        return True

    except mysql.connector.Error as err:
        print(f"!!! MySQL Error: {err} !!!")
        print(
            "!!! Check MySQL connection details, if the container port is exposed, and if the 'mysql-server' is running. !!!")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def verify_mongodb():
    print("\n--- Verifying MongoDB Data ---")
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster')
        print("[MongoDB] Connection successful.")

        db = client[MONGO_DB_NAME]
        collection = db[MONGO_COLLECTION]

        print(f"\n[MongoDB] Checking '{MONGO_COLLECTION}' collection...")
        documents_cursor = collection.find().sort("upload_time", -1).limit(5)
        documents = list(documents_cursor)

        if documents:
            total_docs = collection.count_documents({})
            print(f"  Found {total_docs} documents in total. Displaying up to 5 (newest first):")
            for doc in documents:
                print(json.dumps(serialize_doc(doc), indent=2, ensure_ascii=False))
                print("-" * 20)
        else:
            print(f"  No documents found in '{MONGO_COLLECTION}'.")

        print("\n--- MongoDB Verification Complete ---")
        return True

    except ConnectionFailure as e:
        print(f"!!! MongoDB Connection Error: {e} !!!")
        return False
    except OperationFailure as e:
        print(f"!!! MongoDB Operation Error: {e} !!!")
        return False
    except Exception as e:
        print(f"!!! An unexpected error occurred during MongoDB verification: {type(e).__name__}: {e} !!!")
        return False
    finally:
        if client:
            client.close()


def verify_ollama():
    print("\n--- Verifying Ollama AI Service ---")
    try:
        response = requests.get(f"{OLLAMA_API_BASE_URL}/api/tags", timeout=10)
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        if not models:
            print("  [Ollama] No models found.")
            return False

        print(f"  [Ollama] Found {len(models)} model(s):")
        model_found = False
        for model in models:
            print(f"    - Name: {model.get('name')}, Size: {model.get('size')}, Modified: {model.get('modified_at')}")
            if model.get('name') == OLLAMA_EXPECTED_MODEL:
                model_found = True

        if model_found:
            print(f"  [Ollama] SUCCESS: Expected model '{OLLAMA_EXPECTED_MODEL}' is available.")
        else:
            print(f"  [Ollama] FAILURE: Expected model '{OLLAMA_EXPECTED_MODEL}' NOT found.")
            return False

        print("\n--- Ollama Verification Complete ---")
        return True

    except requests.exceptions.ConnectionError:
        print(f"!!! Ollama Connection Error: Could not connect to {OLLAMA_API_BASE_URL}. Is the service running? !!!")
        return False
    except requests.exceptions.Timeout:
        print(f"!!! Ollama Request Timeout: The request to {OLLAMA_API_BASE_URL}/api/tags timed out. !!!")
        return False
    except requests.exceptions.RequestException as e:
        print(f"!!! Ollama API Request Failed: {e} !!!")
        if e.response is not None:
            print(f"Response Status Code: {e.response.status_code}")
            print(f"Response Body: {e.response.text}")
        return False
    except json.JSONDecodeError:
        print(f"!!! Ollama API Error: Could not decode JSON response from /api/tags. !!!")
        print(f"Raw response: {response.text if 'response' in locals() else 'N/A'}")
        return False
    except Exception as e:
        print(f"!!! An unexpected error occurred during Ollama verification: {type(e).__name__}: {e} !!!")
        return False


def verify_grading_service():  # <-- NEW
    print("\n--- Verifying Grading Service ---")
    try:
        response = requests.get(f"{GRADING_API_BASE_URL}/health", timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "ok":
            print(f"  [Grading Service] SUCCESS: Health check passed. Message: {data.get('message')}")
            return True
        else:
            print(f"  [Grading Service] FAILURE: Health check status not 'ok'. Response: {data}")
            return False
    except requests.exceptions.ConnectionError:
        print(
            f"!!! Grading Service Connection Error: Could not connect to {GRADING_API_BASE_URL}. Is the service running? !!!")
        return False
    except requests.exceptions.Timeout:
        print(f"!!! Grading Service Request Timeout: The request to {GRADING_API_BASE_URL}/health timed out. !!!")
        return False
    except requests.exceptions.RequestException as e:
        print(f"!!! Grading Service API Request Failed: {e} !!!")
        return False
    except json.JSONDecodeError:
        print(f"!!! Grading Service API Error: Could not decode JSON response from /health. !!!")
        return False
    except Exception as e:
        print(f"!!! An unexpected error occurred during Grading Service verification: {type(e).__name__}: {e} !!!")
        return False


if __name__ == "__main__":
    print("======== Starting Verification Script ========")

    mysql_ok = verify_mysql()
    mongodb_ok = verify_mongodb()
    ollama_ok = verify_ollama()
    grading_ok = verify_grading_service()  # <-- NEW

    print("\n======== Verification Summary ========")
    print(f"MySQL Verification:      {'SUCCESS' if mysql_ok else 'FAILED'}")
    print(f"MongoDB Verification:    {'SUCCESS' if mongodb_ok else 'FAILED'}")
    print(f"Ollama Verification:     {'SUCCESS' if ollama_ok else 'FAILED'}")
    print(f"Grading Svc Verification:{'SUCCESS' if grading_ok else 'FAILED'}")
    print("======================================")

    if not mysql_ok or not mongodb_ok or not ollama_ok or not grading_ok:
        sys.exit(1)
    else:
        sys.exit(0)