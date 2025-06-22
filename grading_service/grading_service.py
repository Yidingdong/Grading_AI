from flask import Flask, request, jsonify
from flask_restful import Resource, Api
from pymongo import MongoClient, errors as pymongo_errors
from bson import ObjectId
from openai import OpenAI
import os
import time
import logging

app = Flask(__name__)
api = Api(app)

# --- Configuration ---
MONGO_URI = "mongodb://root:example@mongodb-server:27017/?authSource=admin"
MONGO_DB_NAME = "Exams"
MONGO_COLLECTION_NAME = "pdf_submissions"

# Configuration for Seedbox AI API from environment variables
SEEDBOX_API_BASE_URL = os.getenv("SEEDBOX_API_BASE_URL", "https://api.seedbox.ai/v1")
SEEDBOX_CHAT_MODEL = os.getenv("SEEDBOX_CHAT_MODEL", "gpt-4o-mini")  # A valid, default model

# --- Read API Key from Docker Secret ---
api_key = None
try:
    # Docker secrets are mounted at /run/secrets/
    with open('/run/secrets/apikey', 'r') as f:
        api_key = f.read().strip()
except IOError:
    app.logger.error("Could not read API key from Docker secret file: /run/secrets/apikey. Falling back to env var.")
    # Fallback to an environment variable if the secret is not found (useful for local testing)
    api_key = os.getenv("SEEDBOX_API_KEY")

if not api_key:
    app.logger.warning("API key is NOT configured. Grading service API calls will fail.")

# --- OpenAI Client Initialization ---
# Initialize the client to be used by all requests.
# The base_url should already contain the /v1 path from the environment variable.
client = OpenAI(
    base_url=SEEDBOX_API_BASE_URL,
    api_key=api_key
)

# --- Logging and DB Connection (remains the same) ---
if not app.debug and not app.testing:
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

mongo_client = None


def get_mongo_client():
    global mongo_client
    # Simple singleton pattern for the DB client
    if mongo_client is None or mongo_client.is_mongos:  # Check if client is valid
        try:
            app.logger.info(f"Attempting to connect to MongoDB at {MONGO_URI}")
            client_conn = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            client_conn.admin.command('ping')
            mongo_client = client_conn
            app.logger.info("MongoDB connection successful.")
        except pymongo_errors.ConnectionFailure as e:
            app.logger.error(f"MongoDB connection failed: {e}")
            mongo_client = None
            raise
    return mongo_client


class GradeDocument(Resource):
    def post(self):
        data = request.get_json()
        if not data or 'document_id' not in data:
            return {'message': 'Missing document_id (for student answer sheet)'}, 400

        student_answer_doc_id_str = data['document_id']
        try:
            student_answer_doc_oid = ObjectId(student_answer_doc_id_str)
        except Exception:
            return {'message': f'Invalid student_answer_doc_id format: {student_answer_doc_id_str}'}, 400

        try:
            # Step 1: Fetch content from MongoDB
            mongo_conn = get_mongo_client()
            db = mongo_conn[MONGO_DB_NAME]
            collection = db[MONGO_COLLECTION_NAME]

            # Fetch the student's answer sheet document
            student_doc = collection.find_one({"_id": student_answer_doc_oid})
            if not student_doc:
                return {'message': f'Student answer sheet with ID {student_answer_doc_id_str} not found'}, 404

            student_answer_content = student_doc.get("content", "")
            original_student_filename = student_doc.get("original_pdf_filename", "Unknown Student Answer")
            course_id = student_doc.get("course_id")
            if not course_id:
                return {'message': f'Missing "course_id" in student answer sheet metadata'}, 400

            # Fetch the latest Question Paper and Reference Material for the course
            qp_doc = collection.find_one(
                {"course_id": course_id, "category": "question_paper"},
                sort=[("processing_timestamp", -1)]
            )
            ref_doc = collection.find_one(
                {"course_id": course_id, "category": "reference_material"},
                sort=[("processing_timestamp", -1)]
            )

            question_paper_content = qp_doc.get("content",
                                                "No question paper content was available for grading.") if qp_doc else "No question paper found for this course."
            reference_material_content = ref_doc.get("content",
                                                     "No reference material content was available for grading.") if ref_doc else "No reference material found for this course."

        except pymongo_errors.PyMongoError as e:
            app.logger.error(f"MongoDB error fetching documents: {e}")
            return {'message': f'MongoDB error: {e}'}, 500
        except Exception as e:
            app.logger.error(f"Unexpected error fetching documents: {e}", exc_info=True)
            return {'message': f'Unexpected internal error'}, 500

        # Step 2: Construct the new, detailed prompt for the AI
        prompt_content = f"""You are an expert AI grading assistant. Your task is to evaluate the student's answer sheet based on the provided question paper and reference material.

GRADING CRITERIA AND WEIGHTS:
1.  **Relevance & Accuracy against Question Paper (Weight: 70%)**: How well does the answer address the questions? Is it factually correct and complete?
2.  **Use of Reference Material (Weight: 10%)**: Does the answer correctly incorporate or align with the provided reference material?
3.  **Grammar & Word Choice (Weight: 10%)**: Is the language clear, professional, and free of grammatical errors?
4.  **Logical Structure (Weight: 10%)**: Is the answer well-organized, coherent, and easy to follow?

--- QUESTION PAPER ---
{question_paper_content}
--- END OF QUESTION PAPER ---

--- REFERENCE MATERIAL ---
{reference_material_content}
--- END OF REFERENCE MATERIAL ---

--- STUDENT'S ANSWER SHEET (Original Filename: {original_student_filename}) ---
{student_answer_content}
--- END OF STUDENT'S ANSWER SHEET ---

TASK:
Provide a detailed evaluation for each of the four criteria. Then, provide an overall numerical grade from 1 to 100, considering the specified weights.

RESPONSE FORMAT (Strictly follow this format):
**Overall Grade:** [Score from 1-100]

**Evaluation - Question Paper (70%):**
[Detailed justification and observations regarding the student's answer against the question paper.]

**Evaluation - Reference Material (10%):**
[Detailed justification and observations regarding the student's use of or consistency with the reference material.]

**Evaluation - Grammar & Word Choice (10%):**
[Detailed justification and observations regarding the grammar and vocabulary used in the student's answer.]

**Evaluation - Logical Structure (10%):**
[Detailed justification and observations regarding the organization, flow, and coherence of the student's answer.]
"""

        # Step 3: Call the Seedbox AI API using the OpenAI SDK
        try:
            if not api_key:
                app.logger.error("Cannot make API call: Seedbox API key is not configured.")
                return {'message': 'Grading service is not configured with an API key.'}, 503

            app.logger.info(
                f"Sending prompt to model '{SEEDBOX_CHAT_MODEL}' for student answer {student_answer_doc_id_str}")

            chat_completion = client.chat.completions.create(
                model=SEEDBOX_CHAT_MODEL,
                messages=[
                    {"role": "user", "content": prompt_content}
                ]
            )

            ai_evaluation = chat_completion.choices[0].message.content
            app.logger.info(f"Received evaluation for student answer {student_answer_doc_id_str}")

            return {
                'document_id': student_answer_doc_id_str,
                'evaluation_by_model': SEEDBOX_CHAT_MODEL,
                'evaluation_result': ai_evaluation,  # Key the frontend expects
            }, 200

        except Exception as e:
            app.logger.error(f"Error communicating with AI API for document {student_answer_doc_id_str}: {e}",
                             exc_info=True)
            return {'message': f'Error communicating with AI service: {e}'}, 502


@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "message": "Grading service is running"}), 200


api.add_resource(GradeDocument, '/grade_document')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)