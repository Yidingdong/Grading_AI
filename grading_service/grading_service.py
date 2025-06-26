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

# Configuration for Seedbox AI API from environment variables
SEEDBOX_API_BASE_URL = os.getenv("SEEDBOX_API_BASE_URL", "https://api.seedbox.ai")
SEEDBOX_CHAT_MODEL = os.getenv("SEEDBOX_CHAT_MODEL", "gpt-4o-mini")

# Define the weights for each grading category
GRADING_WEIGHTS = {
    "relevance_accuracy": 0.70,
    "reference_material": 0.10,
    "grammar_word_choice": 0.10,
    "logical_structure": 0.10,
}

# --- Read API Key from Docker Secret ---
api_key = None
try:
    with open('/run/secrets/apikey', 'r') as f:
        api_key = f.read().strip()
except IOError:
    app.logger.error("Could not read API key from Docker secret file. Falling back to env var.")
    api_key = os.getenv("SEEDBOX_API_KEY")

if not api_key:
    app.logger.warning("API key is NOT configured. Grading service API calls will fail.")

# --- OpenAI Client Initialization ---
client = OpenAI(
    base_url=SEEDBOX_API_BASE_URL,
    api_key=api_key
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
            return {'message': 'Missing document_id (for student answer sheet)'}, 400

        student_answer_doc_id_str = data['document_id']
        try:
            student_answer_doc_oid = ObjectId(student_answer_doc_id_str)
        except Exception:
            return {'message': f'Invalid student_answer_doc_id format: {student_answer_doc_id_str}'}, 400

        try:
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

            qp_doc = collection.find_one(
                {"course_id": course_id, "category": "question_paper"},
                sort=[("processing_timestamp", -1)]
            )
            ref_doc = collection.find_one(
                {"course_id": course_id, "category": "reference_material"},
                sort=[("processing_timestamp", -1)]
            )
            question_paper_content = qp_doc.get("content", "No question paper content was available.") if qp_doc else "No question paper found for this course."
            reference_material_content = ref_doc.get("content", "No reference material content was available.") if ref_doc else "No reference material found for this course."
        except pymongo_errors.PyMongoError as e:
            app.logger.error(f"MongoDB error fetching documents: {e}")
            return {'message': f'MongoDB error: {e}'}, 500
        except Exception as e:
            app.logger.error(f"Unexpected error fetching documents: {e}", exc_info=True)
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
  "relevance_accuracy": {{
    "score": <integer from 0-100>,
    "justification": "<Detailed justification and observations for this category.>"
  }},
  "reference_material": {{
    "score": <integer from 0-100>,
    "justification": "<Detailed justification and observations for this category.>"
  }},
  "grammar_word_choice": {{
    "score": <integer from 0-100>,
    "justification": "<Detailed justification and observations for this category.>"
  }},
  "logical_structure": {{
    "score": <integer from 0-100>,
    "justification": "<Detailed justification and observations for this category.>"
  }}
}}
"""
        try:
            if not api_key:
                app.logger.error("Cannot make API call: Seedbox API key is not configured.")
                return {'message': 'Grading service is not configured with an API key.'}, 503

            app.logger.info(f"Sending prompt to model '{SEEDBOX_CHAT_MODEL}' for student answer {student_answer_doc_id_str}")
            chat_completion = client.chat.completions.create(
                model=SEEDBOX_CHAT_MODEL,
                messages=[{"role": "user", "content": prompt_content}],
                response_format={"type": "json_object"}
            )
            ai_response_str = chat_completion.choices[0].message.content
            app.logger.info(f"Received raw JSON response for {student_answer_doc_id_str}")

            try:
                ai_data = json.loads(ai_response_str)
            except json.JSONDecodeError:
                app.logger.error(f"Failed to decode AI JSON response for {student_answer_doc_id_str}. Response: {ai_response_str}")
                return {'message': 'AI returned malformed data. Could not parse evaluation.'}, 502

            final_grade = (
                ai_data.get("relevance_accuracy", {}).get("score", 0) * GRADING_WEIGHTS["relevance_accuracy"] +
                ai_data.get("reference_material", {}).get("score", 0) * GRADING_WEIGHTS["reference_material"] +
                ai_data.get("grammar_word_choice", {}).get("score", 0) * GRADING_WEIGHTS["grammar_word_choice"] +
                ai_data.get("logical_structure", {}).get("score", 0) * GRADING_WEIGHTS["logical_structure"]
            )
            final_grade = round(final_grade)

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

            update_result = collection.update_one(
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
            if update_result.modified_count > 0:
                app.logger.info(f"Successfully saved structured AI evaluation to MongoDB for document {student_answer_doc_id_str}.")
            else:
                app.logger.warning(f"AI evaluation was generated but failed to save to MongoDB for document {student_answer_doc_id_str}.")

            return {
                'document_id': student_answer_doc_id_str,
                'message': 'Grading successful',
                'evaluation_details': ai_evaluation_details
            }, 200

        except Exception as e:
            app.logger.error(f"Error during AI grading process for document {student_answer_doc_id_str}: {e}", exc_info=True)
            return {'message': f'Error communicating with AI service: {e}'}, 502

@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "message": "Grading service is running"}), 200

api.add_resource(GradeDocument, '/grade_document')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)