import fitz  # PyMuPDF
from pymongo import MongoClient, errors as pymongo_errors
from bson.objectid import ObjectId
import os
from datetime import datetime
import logging
from flask import Flask, request, jsonify
from flask_restful import Resource, Api
import tempfile
import gridfs

# --- Logger Setup ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --- Flask App Setup ---
app = Flask(__name__)
api = Api(app)

# --- MongoDB Configuration ---
MONGO_HOST_ENV = os.getenv("MONGO_HOST", "mongodb-server")

MONGO_FRONTEND_USER = os.getenv("MONGO_USER_FRONTEND", "root")
MONGO_FRONTEND_PASSWORD = os.getenv("MONGO_PASSWORD_FRONTEND", "example")
MONGO_FRONTEND_DB_NAME = os.getenv("MONGO_DB_NAME_FRONTEND", "grading_ai_frontend")
MONGO_FRONTEND_URI = f"mongodb://{MONGO_FRONTEND_USER}:{MONGO_FRONTEND_PASSWORD}@{MONGO_HOST_ENV}:27017/{MONGO_FRONTEND_DB_NAME}?authSource=admin"

MONGO_EXAMS_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME", "root")
MONGO_EXAMS_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "example")
MONGO_EXAMS_DB_NAME = "Exams"
MONGO_EXAMS_COLLECTION_NAME = "pdf_submissions"
MONGO_EXAMS_URI = f"mongodb://{MONGO_EXAMS_USER}:{MONGO_EXAMS_PASSWORD}@{MONGO_HOST_ENV}:27017/{MONGO_EXAMS_DB_NAME}?authSource=admin"


# --- Core OCR and DB Logic ---
def pdf_to_markdown(pdf_path, ocr_threshold=20, language="eng", ocr_dpi=300):
    markdown_content = ""
    doc = None
    try:
        doc = fitz.open(pdf_path)
        logger.info(f"Processing PDF: {pdf_path} with {len(doc)} pages. OCR DPI: {ocr_dpi}, Lang: {language}")
        for i, page in enumerate(doc):
            page_num = i + 1
            logger.debug(f" Processing page {page_num}...")
            text = page.get_text("text")
            extracted_text = text.strip() if text else ""
            if len(extracted_text) < ocr_threshold:
                logger.info(
                    f"  Page {page_num}: Standard text minimal ({len(extracted_text)} chars). Attempting OCR...")
                try:
                    tp_ocr = page.get_textpage_ocr(language=language, dpi=ocr_dpi, flags=3, full=True)
                    if tp_ocr:
                        ocr_text = page.get_text("text", textpage=tp_ocr)
                        extracted_text = ocr_text.strip() if ocr_text else ""
                        logger.info(f"  Page {page_num}: OCR successful ({len(extracted_text)} chars).")
                    else:
                        logger.info(f"  Page {page_num}: OCR TextPage generation failed.")
                        extracted_text = ""
                except RuntimeError as rt_err:
                    logger.error(f"  Page {page_num}: OCR attempt failed with RuntimeError: {rt_err}")
                    extracted_text = ""
                except Exception as ocr_error:
                    logger.error(f"  Page {page_num}: OCR failed with unexpected error: {ocr_error}")
                    extracted_text = ""
            else:
                logger.info(f"  Page {page_num}: Standard text extraction sufficient ({len(extracted_text)} chars).")
            markdown_content += extracted_text + "\n\n"
        return markdown_content.strip()
    except Exception as e:
        logger.error(f"PDF processing failed for {pdf_path}: {e}")
        raise
    finally:
        if doc: doc.close()


def store_ocr_in_exams_db(data):
    client = None
    try:
        client = MongoClient(MONGO_EXAMS_URI)
        client.admin.command('ping')
        db = client[MONGO_EXAMS_DB_NAME]
        collection = db[MONGO_EXAMS_COLLECTION_NAME]

        # Check if a document with this processed_from_gridfs_id already exists to avoid duplicates
        # This is important if the API might be called multiple times for the same student submission
        if data.get("processed_from_gridfs_id"):
            existing_doc = collection.find_one({"processed_from_gridfs_id": data.get("processed_from_gridfs_id")})
            if existing_doc:
                logger.info(
                    f"Submission from GridFS ID {data.get('processed_from_gridfs_id')} has already been processed. Returning existing Exams DB ID: {existing_doc['_id']}")
                return existing_doc['_id']

        result = collection.insert_one(data)
        logger.info(
            f"OCR data stored in '{MONGO_EXAMS_DB_NAME}.{MONGO_EXAMS_COLLECTION_NAME}'. Inserted ID: {result.inserted_id}")
        return result.inserted_id
    except pymongo_errors.ConnectionFailure as e:
        logger.error(f"Exams DB ConnectionFailure: {e}")
        raise
    except Exception as e:
        logger.error(f"Exams DB store operation failed: {e}")
        raise
    finally:
        if client: client.close()


# --- Flask Resource ---
class ProcessStudentSubmission(Resource):
    def post(self):
        json_data = request.get_json()
        if not json_data:
            return {"message": "Request body must be JSON"}, 400

        gridfs_file_id_str = json_data.get('gridfs_file_id')
        student_name = json_data.get('student_name', "Unknown Student")
        student_id_str = json_data.get('student_id')
        uploader_username = json_data.get('uploader_username')
        teacher_username = json_data.get('teacher_username')  # Teacher of the course
        course_name = json_data.get('course_name')
        original_filename_from_meta = json_data.get('original_filename', "unknown.pdf")
        lang = json_data.get('lang', "eng")

        if not gridfs_file_id_str:
            return {"message": "Missing 'gridfs_file_id' in request"}, 400
        # Other required fields for context
        if not (student_id_str and uploader_username and course_name and teacher_username):
            return {
                "message": "Missing required metadata: student_id, uploader_username, course_name, teacher_username"}, 400

        logger.info(
            f"Received API request to process GridFS file ID: {gridfs_file_id_str} for student: {student_name} (ID: {student_id_str}), course: {course_name}")

        frontend_client = None
        temp_pdf_path = None
        try:
            frontend_client = MongoClient(MONGO_FRONTEND_URI)
            frontend_db = frontend_client[MONGO_FRONTEND_DB_NAME]
            frontend_fs = gridfs.GridFS(frontend_db)

            gridfs_object_id = ObjectId(gridfs_file_id_str)
            grid_out = frontend_fs.get(gridfs_object_id)  # Throws NoFile if not found

            # Save GridFS file content to a temporary local file for PyMuPDF
            # Using a context manager for the temporary file is safer
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmpfile_obj:
                tmpfile_obj.write(grid_out.read())
                temp_pdf_path = tmpfile_obj.name

            logger.info(
                f"File '{original_filename_from_meta}' (GridFS ID: {gridfs_file_id_str}) retrieved from GridFS and saved to temp path: {temp_pdf_path}")

            markdown_content = pdf_to_markdown(pdf_path=temp_pdf_path, language=lang)
            if not markdown_content:
                logger.warning(
                    f"OCR processing resulted in empty content for {original_filename_from_meta}. Storing empty content.")
                # An entry will still be made, but content will be empty.

            submission_data_for_exams_db = {
                "student_name": student_name,
                "student_id": student_id_str,
                "uploader_username": uploader_username,  # student's username
                "teacher_username": teacher_username,  # course teacher's username
                "course": course_name,
                "category": "answer_sheet",
                "content": markdown_content,
                "original_pdf_filename": original_filename_from_meta,
                "processed_from_gridfs_id": gridfs_file_id_str,  # Link back to the GridFS source in frontend DB
                "processing_timestamp": datetime.utcnow()  # Renamed from upload_time for clarity
            }

            inserted_id_in_exams = store_ocr_in_exams_db(submission_data_for_exams_db)

            return {
                "message": "Student submission processed and OCR'd successfully.",
                "original_filename": original_filename_from_meta,
                "exams_db_document_id": str(inserted_id_in_exams)
            }, 200

        except gridfs.errors.NoFile:
            logger.error(f"File with GridFS ID {gridfs_file_id_str} not found in '{MONGO_FRONTEND_DB_NAME}'.")
            return {"message": f"File not found in GridFS: {gridfs_file_id_str}"}, 404
        except pymongo_errors.ConnectionFailure as e:
            logger.critical(f"MongoDB connection failed during processing: {e}")
            return {"message": f"MongoDB connection error: {e}"}, 503
        except Exception as e:
            logger.error(f"Error processing submission from GridFS ID {gridfs_file_id_str}: {e}", exc_info=True)
            return {"message": f"Internal server error: {e}"}, 500
        finally:
            if frontend_client: frontend_client.close()
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                try:
                    os.remove(temp_pdf_path); logger.debug(f"Temporary file {temp_pdf_path} removed.")
                except Exception as e_remove:
                    logger.warning(f"Could not remove temporary file {temp_pdf_path}: {e_remove}")


@app.route('/health')
def health_check():
    # Potentially add quick pings to MongoDB instances here for a more robust health check
    return jsonify({"status": "ok", "message": "PDF Processor service is healthy"}), 200


api.add_resource(ProcessStudentSubmission, '/process_submission')


# This part is for when the script was run with CLI arguments.
# It's not strictly needed for the Flask service but can be kept for standalone testing or other uses.
def main_cli():
    import argparse  # Keep import local if only for CLI
    parser = argparse.ArgumentParser(description="CLI: Extract text/OCR PDF and upload to MongoDB with metadata")
    parser.add_argument("--pdf", required=True,
                        help="Path to PDF file (e.g., /app/pdfs/yourfile.pdf for container path)")
    # ... other CLI arguments as before ...
    parser.add_argument("--username", required=True, help="Uploader's username")
    parser.add_argument("--course", required=True, help="Course name")
    parser.add_argument("--student-name", required=True, help="Name of the student (or N/A)")
    parser.add_argument("--student-id", help="Student ID (optional, but recommended for answer_sheet)")
    parser.add_argument("--teacher", required=True, help="Teacher's username for the course")
    parser.add_argument("--category", required=True, choices=["question_paper", "answer_sheet", "reference_material"],
                        help="Type of document")
    parser.add_argument("--lang", default="eng", help="Tesseract language for OCR (e.g., eng, deu)")
    parser.add_argument("--ocr-threshold", type=int, default=20, help="Char count threshold for OCR attempt")
    parser.add_argument("--ocr-dpi", type=int, default=300, help="DPI for OCR rendering")
    args = parser.parse_args()

    logger.info(f"--- Starting PDF Processing (CLI Mode) ---")
    logger.info(f" Arguments: {vars(args)}")

    if not os.path.exists(args.pdf):
        logger.error(f"Input PDF file not found: {args.pdf}")
        raise FileNotFoundError(f"Input PDF file not found: {args.pdf}")
    try:
        markdown_content = pdf_to_markdown(pdf_path=args.pdf, ocr_threshold=args.ocr_threshold, language=args.lang,
                                           ocr_dpi=args.ocr_dpi)
        if not markdown_content: logger.warning(f"Extracted content is empty for {args.pdf}.")

        submission_data = {
            "student_name": args.student_name, "student_id": args.student_id if args.student_id else None,
            "uploader_username": args.username, "teacher_username": args.teacher,
            "course": args.course, "category": args.category, "content": markdown_content,
            "original_pdf_filename": os.path.basename(args.pdf), "upload_time": datetime.utcnow()
        }
        inserted_id = store_ocr_in_exams_db(submission_data)  # Store in Exams DB
        logger.info(f"--- CLI Success! PDF processed, data in MongoDB. Submission ID: {inserted_id} ---")
    except Exception as e:
        logger.error(f"!!! CLI Error: {type(e).__name__} - {str(e)} !!!", exc_info=True)
        exit(1)


if __name__ == '__main__':
    # Check if script is run with 'flask run' or directly 'python script.py'
    # If 'FLASK_APP' is set (standard for `flask run`), it implies Flask mode.
    # Otherwise, if specific CLI args might be expected, one could check for them.
    # For simplicity, the Docker CMD explicitly runs `python pdf_to_mongodb.py` which starts Flask.
    # If you wanted to support both CLI and Flask from one `python script.py` call, you'd add argument parsing here.

    # Default to running Flask app
    logger.info(f"Starting PDF Processor service API on port 5003...")
    # Use FLASK_DEBUG from env for app.run, default to False (production)
    flask_debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(host='0.0.0.0', port=5003, debug=flask_debug_mode)