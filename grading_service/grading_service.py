from flask import Flask, request, jsonify
from flask_restful import Resource, Api
from pymongo import MongoClient, errors as pymongo_errors
from bson import ObjectId
import requests
import os
import time
import logging

app = Flask(__name__)
api = Api(app)

MONGO_HOST_ENV = os.getenv("MONGO_HOST", "mongodb-server")  # Added for consistency
MONGO_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME", "root")
MONGO_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "example")

MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST_ENV}:27017/?authSource=admin"
MONGO_DB_NAME = "Exams"  # Database where OCR'd content is stored
MONGO_COLLECTION_NAME = "pdf_submissions"  # Collection for OCR'd content

OLLAMA_API_BASE_URL = os.getenv("OLLAMA_API_BASE_URL", "http://ollama-ai-server:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "granite3.2-vision:latest")  # Use env var or default

MAX_RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 3

if not app.debug and not app.testing:
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

mongo_client = None


def get_mongo_client():
    global mongo_client
    if mongo_client is None or mongo_client.admin.command('ping').get('ok') != 1.0:  # Check if client is still valid
        try:
            app.logger.info(
                f"Attempting to connect to MongoDB at {MONGO_URI.split('@')[-1]}")  # Log without credentials
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, UuidRepresentation='standard')
            client.admin.command('ping')
            mongo_client = client
            app.logger.info("MongoDB connection successful.")
        except pymongo_errors.ConnectionFailure as e:
            app.logger.error(f"MongoDB connection failed: {e}")
            mongo_client = None  # Reset client on failure
            raise
        except Exception as e_generic:  # Catch other potential errors during client init
            app.logger.error(f"MongoDB client initialization error: {e_generic}")
            mongo_client = None
            raise
    return mongo_client


def init_db_connection():  # Tries to establish initial connection
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            get_mongo_client()  # Attempt to get/create client
            if mongo_client:
                app.logger.info("MongoDB connection initialized for service startup.")
                return
        except Exception:  # Catch any exception from get_mongo_client
            app.logger.warning(
                f"MongoDB connection attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} failed during init. Retrying in {RETRY_DELAY_SECONDS}s...")
            time.sleep(RETRY_DELAY_SECONDS)
    app.logger.error(
        "Failed to connect to MongoDB after multiple retries during service startup. Grading service may not function optimally.")


class GradeDocument(Resource):
    def post(self):
        data = request.get_json()
        if not data or 'document_id' not in data:
            return {'message': 'Missing document_id (for student answer sheet) in request body'}, 400

        student_answer_doc_id_str = data['document_id']
        try:
            student_answer_doc_oid = ObjectId(student_answer_doc_id_str)
        except Exception:
            return {'message': f'Invalid student_answer_doc_id format: {student_answer_doc_id_str}'}, 400

        student_answer_content = ""
        question_paper_content = ""
        reference_material_content = ""
        original_student_filename = "Unknown Student Answer"
        course_id_for_grading = None

        try:
            client = get_mongo_client()
            if not client:
                app.logger.error("MongoDB connection not available at time of request.")
                return {'message': 'MongoDB connection not available, please try again later.'}, 503

            db = client[MONGO_DB_NAME]
            collection = db[MONGO_COLLECTION_NAME]

            # 1. Fetch Student's Answer Sheet
            student_answer_doc = collection.find_one({"_id": student_answer_doc_oid, "category": "answer_sheet"})
            if not student_answer_doc:
                return {
                    'message': f'Student answer sheet with ID {student_answer_doc_id_str} not found or not category "answer_sheet"'}, 404

            student_answer_content = student_answer_doc.get("content", "").strip()
            if not student_answer_content:  # If content is empty string after strip
                app.logger.warning(f'Student answer sheet {student_answer_doc_id_str} has empty content.')
                # Decide if to proceed or error out. For now, we proceed.
                # return {'message': f'No "content" in student answer sheet {student_answer_doc_id_str}'}, 400

            original_student_filename = student_answer_doc.get("original_pdf_filename", "Unknown Student Answer")
            course_id_for_grading = student_answer_doc.get("course_id")
            if not course_id_for_grading:
                return {
                    'message': f'Missing "course_id" in student answer sheet metadata (ID: {student_answer_doc_id_str})'}, 400

            # 2. Fetch latest Question Paper for the course
            question_paper_doc = collection.find_one(
                {"course_id": course_id_for_grading, "category": "question_paper"},
                sort=[("processing_timestamp", -1)]
            )
            if question_paper_doc and question_paper_doc.get("content"):
                question_paper_content = question_paper_doc.get("content").strip()
                app.logger.info(f"Found QP for course {course_id_for_grading}, ID: {question_paper_doc['_id']}")
            else:
                app.logger.warning(
                    f"No suitable Question Paper content found for course_id: {course_id_for_grading}. Proceeding without it.")

            # 3. Fetch latest Reference Material for the course
            reference_material_doc = collection.find_one(
                {"course_id": course_id_for_grading, "category": "reference_material"},
                sort=[("processing_timestamp", -1)]
            )
            if reference_material_doc and reference_material_doc.get("content"):
                reference_material_content = reference_material_doc.get("content").strip()
                app.logger.info(
                    f"Found Ref Material for course {course_id_for_grading}, ID: {reference_material_doc['_id']}")
            else:
                app.logger.warning(
                    f"No suitable Reference Material content found for course_id: {course_id_for_grading}. Proceeding without it.")

        except pymongo_errors.PyMongoError as e:
            app.logger.error(f"MongoDB error: {e}")
            return {'message': f'MongoDB error: {e}'}, 500
        except Exception as e:  # Catch broader exceptions during DB fetch
            app.logger.error(f"Unexpected error fetching documents: {e}", exc_info=True)
            return {'message': f'Unexpected error: {e}'}, 500

        # 4. Construct the new comprehensive prompt
        # Ensure that even if content is empty, the sections are still present.
        qp_text_for_prompt = question_paper_content if question_paper_content else "No question paper content was available for grading."
        ref_text_for_prompt = reference_material_content if reference_material_content else "No reference material content was available for grading."
        student_text_for_prompt = student_answer_content if student_answer_content else "The student's answer sheet was empty or contained no processable text."

        prompt = f"""You are an AI grading assistant. Your task is to evaluate the student's answer sheet based on the provided question paper and reference material.

GRADING CRITERIA AND WEIGHTS:
1.  Relevance, Accuracy, and Completeness against Question Paper (Weight: 70%)
2.  Appropriate Use of and Consistency with Reference Material (Weight: 10%)
3.  Grammar and Choice of Words in Student's Answer (Weight: 10%)
4.  Logical Structure and Coherence of Student's Answer (Weight: 10%)

--- QUESTION PAPER ---
{qp_text_for_prompt}
--- END OF QUESTION PAPER ---

--- REFERENCE MATERIAL ---
{ref_text_for_prompt}
--- END OF REFERENCE MATERIAL ---

--- STUDENT'S ANSWER SHEET (Original Filename: {original_student_filename}) ---
{student_text_for_prompt}
--- END OF STUDENT'S ANSWER SHEET ---

TASK:
Provide a detailed evaluation for each of the four criteria.
Then, provide an overall numerical grade from 1 to 100, considering the specified weights.

RESPONSE FORMAT:
Overall Grade: [Score from 1-100]

Evaluation - Question Paper (70%):
[Detailed justification and observations regarding the student's answer against the question paper.]

Evaluation - Reference Material (10%):
[Detailed justification and observations regarding the student's use of or consistency with the reference material. Note if not applicable due to missing material.]

Evaluation - Grammar & Word Choice (10%):
[Detailed justification and observations regarding the grammar and vocabulary used in the student's answer.]

Evaluation - Logical Structure (10%):
[Detailed justification and observations regarding the organization, flow, and coherence of the student's answer.]
"""

        ollama_payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2}  # Lower temperature for more deterministic/factual grading
        }

        try:
            app.logger.info(
                f"Sending comprehensive prompt for student answer {student_answer_doc_id_str} (course {course_id_for_grading}) to Ollama model {OLLAMA_MODEL}.")
            # Increased timeout for potentially longer prompts/processing
            response = requests.post(f"{OLLAMA_API_BASE_URL}/api/generate", json=ollama_payload, timeout=300)
            response.raise_for_status()
            ollama_response_data = response.json()
            ai_evaluation = ollama_response_data.get("response", "No response text from AI.")

            app.logger.info(f"Received evaluation from Ollama for student answer {student_answer_doc_id_str}.")
            return {
                'student_answer_document_id': student_answer_doc_id_str,
                'original_student_filename': original_student_filename,
                'course_id': course_id_for_grading,
                'evaluation_by_model': OLLAMA_MODEL,
                'evaluation_result_structured': ai_evaluation,
                'ollama_full_response': ollama_response_data
            }, 200

        except requests.exceptions.Timeout:
            app.logger.error(f"Timeout connecting to Ollama for document {student_answer_doc_id_str}")
            return {'message': 'Timeout connecting to Ollama grading service'}, 504
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Error connecting to Ollama for document {student_answer_doc_id_str}: {e}")
            error_detail = str(e)
            if e.response is not None:
                error_detail += f" - Response: {e.response.text[:200]}"
            return {'message': f'Error communicating with Ollama AI service: {error_detail}'}, 502
        except Exception as e:
            app.logger.error(
                f"Unexpected error during Ollama interaction for document {student_answer_doc_id_str}: {e}",
                exc_info=True)
            return {'message': f'Unexpected error during AI grading: {e}'}, 500


@app.route('/health')
def health_check():
    # More robust health check: try to ping MongoDB
    try:
        client = get_mongo_client()
        if client and client.admin.command('ping').get('ok') == 1.0:
            return jsonify({"status": "ok", "message": "Grading service is running and MongoDB is connected"}), 200
        else:
            return jsonify(
                {"status": "error", "message": "Grading service is running but MongoDB connection failed ping"}), 503
    except Exception as e:
        app.logger.error(f"Health check failed to connect to MongoDB: {e}")
        return jsonify(
            {"status": "error", "message": f"Grading service is running but MongoDB connection error: {e}"}), 503


api.add_resource(GradeDocument, '/grade_document')

if __name__ == '__main__':
    init_db_connection()  # Attempt to connect to DB at startup
    app.run(host='0.0.0.0', port=5002)