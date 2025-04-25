import mysql.connector
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import json
from bson import ObjectId # Import ObjectId
from datetime import datetime # Import datetime
import sys

# --- Configuration ---
# Assumes databases are running in Docker with ports exposed to localhost

# MySQL Configuration
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306 # Default MySQL port
MYSQL_USER = "user"
MYSQL_PASSWORD = "password"
MYSQL_DB = "Informations"

# MongoDB Configuration
MONGO_HOST = "localhost"
MONGO_PORT = 27017 # Default MongoDB port
MONGO_USER = "root"
MONGO_PASSWORD = "example"
MONGO_DB_NAME = "Exams"
MONGO_COLLECTION = "pdf_submissions"
# MongoDB connection string - adjust authSource if needed (often 'admin')
MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"

# --- Helper Function to serialize MongoDB ObjectId and datetime ---
def serialize_doc(doc):
    """Converts MongoDB ObjectId and datetime objects to strings for JSON serialization."""
    if isinstance(doc, dict):
        return {k: serialize_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_doc(elem) for elem in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    # **** ADDED THIS BLOCK TO HANDLE DATETIME ****
    elif isinstance(doc, datetime):
        return doc.isoformat() # Convert datetime to ISO 8601 string format
    # *********************************************
    else:
        return doc

# --- Verification Functions ---

def verify_mysql():
    """Connects to MySQL and verifies data in users, courses, and student_course tables."""
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
        cursor.execute("SELECT id, username, user_type FROM users;")
        users = cursor.fetchall()
        if users:
            for user in users:
                print(f"  {user}")
        else:
            print("  No users found.")

        print("\n[MySQL] Checking 'courses' table...")
        cursor.execute("SELECT * FROM courses;")
        courses = cursor.fetchall()
        if courses:
            for course in courses:
                print(f"  {course}")
        else:
            print("  No courses found.")

        print("\n[MySQL] Checking 'student_course' table (assignments)...")
        cursor.execute("SELECT * FROM student_course;")
        assignments = cursor.fetchall()
        if assignments:
            for assignment in assignments:
                print(f"  {assignment}")
        else:
            print("  No student assignments found.")

        print("\n--- MySQL Verification Complete ---")
        return True

    except mysql.connector.Error as err:
        print(f"!!! MySQL Error: {err} !!!")
        print("!!! Check MySQL connection details and if the container port is exposed. !!!")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

def verify_mongodb():
    """Connects to MongoDB and verifies data in the pdf_submissions collection."""
    print("\n--- Verifying MongoDB Data ---")
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster')
        print("[MongoDB] Connection successful.")

        db = client[MONGO_DB_NAME]
        collection = db[MONGO_COLLECTION]

        print(f"\n[MongoDB] Checking '{MONGO_COLLECTION}' collection...")
        documents_cursor = collection.find().limit(10)
        documents = list(documents_cursor)

        if documents:
            count = collection.count_documents({}) # Get count separately
            print(f"  Found {count} documents in total. Displaying up to 10:")
            for doc in documents:
                # Apply the updated serializer before printing
                print(json.dumps(serialize_doc(doc), indent=4))
        else:
            print(f"  No documents found in '{MONGO_COLLECTION}'.")

        print("\n--- MongoDB Verification Complete ---")
        return True

    except ConnectionFailure as e:
        print(f"!!! MongoDB Connection Error: Could not connect to MongoDB at {MONGO_HOST}:{MONGO_PORT}. !!!")
        print(f"!!! Error details: {e} !!!")
        print("!!! Check MongoDB URI, credentials, and if the container port is exposed. !!!")
        return False
    except OperationFailure as e:
        print(f"!!! MongoDB Operation Error: Authentication failed or operation forbidden. !!!")
        print(f"!!! Error details: {e} !!!")
        print("!!! Check MongoDB credentials and authSource in MONGO_URI. !!!")
        return False
    except Exception as e:
        # Print the actual exception type and message for better debugging
        print(f"!!! An unexpected error occurred during MongoDB verification: {type(e).__name__}: {e} !!!")
        return False
    finally:
        if client:
            client.close()

# --- Main Execution ---
if __name__ == "__main__":
    print("======== Starting Verification Script ========")

    mysql_ok = verify_mysql()
    mongodb_ok = verify_mongodb()

    print("\n======== Verification Summary ========")
    print(f"MySQL Verification:      {'SUCCESS' if mysql_ok else 'FAILED'}")
    print(f"MongoDB Verification:    {'SUCCESS' if mongodb_ok else 'FAILED'}")
    print("======================================")

    if not mysql_ok or not mongodb_ok:
        sys.exit(1)
    else:
        sys.exit(0)