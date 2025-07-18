from flask import Flask, request, jsonify
from flask_restful import Resource, Api
from pymongo import MongoClient, errors as pymongo_errors
from bson import ObjectId
from openai import OpenAI
import os
import time
import logging
from datetime import datetime
import json

app = Flask(__name__)
api = Api(app)

# --- Configuration ---
MONGO_URI = "mongodb://root:example@mongodb-server:27017/?authSource=admin"
MONGO_DB_NAME = "Exams"
MONGO_COLLECTION_NAME = "pdf_submissions"

DEFAULT_API_BASE_URL = os.getenv("SEEDBOX_API_BASE_URL", "https://api.seedbox.ai")
SEEDBOX_CHAT_MODEL = os.getenv("SEEDBOX_CHAT_MODEL", "gpt-4o-mini")

GRADING_WEIGHTS = {
    "relevance_accuracy": 0.70,
    "reference_material": 0.10,
    "grammar_word_choice": 0.10,
    "logical_structure": 0.10,
}

# --- Default API Key Reading ---
default_api_key = None
try:
    with open('/run/secrets/apikey', 'r') as f:
        default_api_key = f.read().strip()
except IOError:
    app.logger.error("Could not read API key from Docker secret file. Falling back to env var.")
    default_api_key = os.getenv("SEEDBOX_API_KEY")

# --- Default OpenAI Client Initialization ---
default_client = OpenAI(
    base_url=DEFAULT_API_BASE_URL,
    api_key=default_api_key
)

# --- Logging and DB Connection ---
if not app.debug and not app.testing:
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

mongo_client = None


def get_mongo_client():
    global mongo_client
    if mongo_client is None or mongo_client.is_mongos:
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
            return {'message': 'Missing document_id'}, 400

        # --- MODIFIED: Handle custom or default API configuration ---
        custom_api_url = data.get("custom_api_url")
        custom_api_key = data.get("custom_api_key")

        request_client = None
        if custom_api_url and custom_api_key:
            app.logger.info(f"Using custom API configuration for this request: URL={custom_api_url}")
            try:
                request_client = OpenAI(base_url=custom_api_url, api_key=custom_api_key)
            except Exception as e:
                app.logger.error(f"Failed to initialize custom OpenAI client: {e}")
                return {'message': f'Invalid custom API configuration: {e}'}, 400
        else:
            app.logger.info("Using default system API configuration.")
            request_client = default_client

        if not (request_client and request_client.api_key):
            app.logger.error("API key is NOT configured for the selected client (default or custom).")
            return {'message': 'Grading service is not configured with an API key.'}, 503

        # --- Document fetching and prompt generation ---
        student_answer_doc_id_str = data['document_id']
        try:
            student_answer_doc_oid = ObjectId(student_answer_doc_id_str)
            mongo_conn = get_mongo_client()
            db = mongo_conn[MONGO_DB_NAME]
            collection = db[MONGO_COLLECTION_NAME]
            student_doc = collection.find_one({"_id": student_answer_doc_oid})
            if not student_doc:
                return {'message': f'Student answer sheet with ID {student_answer_doc_id_str} not found'}, 404

            student_answer_content = student_doc.get("content", "")
            original_student_filename = student_doc.get("original_pdf_filename", "Unknown Student Answer")
            course_id = student_doc.get("course_id")
            if not course_id:
                return {'message': 'Missing "course_id" in student answer sheet metadata'}, 400

            qp_doc = collection.find_one({"course_id": course_id, "category": "question_paper"},
                                         sort=[("processing_timestamp", -1)])
            ref_doc = collection.find_one({"course_id": course_id, "category": "reference_material"},
                                          sort=[("processing_timestamp", -1)])
            question_paper_content = qp_doc.get("content",
                                                "No question paper content was available.") if qp_doc else "No question paper found for this course."
            reference_material_content = ref_doc.get("content",
                                                     "No reference material content was available.") if ref_doc else "No reference material found for this course."
        except pymongo_errors.PyMongoError as e:
            return {'message': f'MongoDB error: {e}'}, 500
        except Exception as e:
            return {'message': 'Unexpected internal error'}, 500

        prompt_content = f"""You are an expert AI grading assistant. Your task is to evaluate the student's answer sheet based on the provided question paper and reference material.

GRADING CRITERIA:
1.  **Relevance & Accuracy against Question Paper**: How well does the answer address the questions? Is it factually correct and complete?
2.  **Use of Reference Material**: Does the answer correctly incorporate or align with the provided reference material?
3.  **Grammar & Word Choice**: Is the language clear, professional, and free of grammatical errors?
4.  **Logical Structure**: Is the answer well-organized, coherent, and easy to follow?

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
Provide a detailed justification for each criterion and a numerical score from 0 to 100 for each. Respond ONLY with a valid JSON object. Do not include any text outside the JSON structure.

JSON RESPONSE FORMAT:
{{
  "relevance_accuracy": {{ "score": <integer>, "justification": "<string>" }},
  "reference_material": {{ "score": <integer>, "justification": "<string>" }},
  "grammar_word_choice": {{ "score": <integer>, "justification": "<string>" }},
  "logical_structure": {{ "score": <integer>, "justification": "<string>" }}
}}
"""

        # --- AI API call and response handling ---
        try:
            chat_completion = request_client.chat.completions.create(
                model=SEEDBOX_CHAT_MODEL,
                messages=[{"role": "user", "content": prompt_content}],
                response_format={"type": "json_object"}
            )
            ai_response_str = chat_completion.choices[0].message.content
            ai_data = json.loads(ai_response_str)

            final_grade = round(
                ai_data.get("relevance_accuracy", {}).get("score", 0) * GRADING_WEIGHTS["relevance_accuracy"] +
                ai_data.get("reference_material", {}).get("score", 0) * GRADING_WEIGHTS["reference_material"] +
                ai_data.get("grammar_word_choice", {}).get("score", 0) * GRADING_WEIGHTS["grammar_word_choice"] +
                ai_data.get("logical_structure", {}).get("score", 0) * GRADING_WEIGHTS["logical_structure"]
            )

            ai_evaluation_details = {
                "final_grade": final_grade,
                "scores": {
                    "relevance_accuracy": ai_data.get("relevance_accuracy", {}).get("score", 0),
                    "reference_material": ai_data.get("reference_material", {}).get("score", 0),
                    "grammar_word_choice": ai_data.get("grammar_word_choice", {}).get("score", 0),
                    "logical_structure": ai_data.get("logical_structure", {}).get("score", 0),
                },
                "justifications": {
                    "relevance_accuracy": ai_data.get("relevance_accuracy", {}).get("justification", "N/A"),
                    "reference_material": ai_data.get("reference_material", {}).get("justification", "N/A"),
                    "grammar_word_choice": ai_data.get("grammar_word_choice", {}).get("justification", "N/A"),
                    "logical_structure": ai_data.get("logical_structure", {}).get("justification", "N/A"),
                }
            }

            collection.update_one(
                {"_id": student_answer_doc_oid},
                {
                    "$set": {
                        "ai_evaluation_details": ai_evaluation_details,
                        "ai_evaluation_model": SEEDBOX_CHAT_MODEL,
                        "ai_evaluation_timestamp": datetime.utcnow()
                    },
                    "$unset": {"ai_evaluation_text": ""}
                }
            )

            return {'document_id': student_answer_doc_id_str, 'evaluation_details': ai_evaluation_details}, 200

        except Exception as e:
            app.logger.error(f"Error during AI grading process for document {student_answer_doc_id_str}: {e}",
                             exc_info=True)
            if "authentication" in str(e).lower() and custom_api_key:
                return {'message': f'Custom API key is invalid or expired. Please check your settings.'}, 401
            return {'message': f'Error communicating with AI service: {e}'}, 502


@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "message": "Grading service is running"}), 200


api.add_resource(GradeDocument, '/grade_document')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
