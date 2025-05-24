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

MONGO_URI = "mongodb://root:example@mongodb-server:27017/?authSource=admin"
MONGO_DB_NAME = "Exams"
MONGO_COLLECTION_NAME = "pdf_submissions"

OLLAMA_API_BASE_URL = "http://ollama-ai-server:11434"
OLLAMA_MODEL = "granite3.2-vision:latest"

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
    if mongo_client is None:
        try:
            app.logger.info(f"Attempting to connect to MongoDB at {MONGO_URI}")
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            mongo_client = client
            app.logger.info("MongoDB connection successful.")
        except pymongo_errors.ConnectionFailure as e:
            app.logger.error(f"MongoDB connection failed: {e}")
            mongo_client = None
            raise
    return mongo_client


def init_db_connection():
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            get_mongo_client()
            if mongo_client:
                return
        except pymongo_errors.ConnectionFailure:
            app.logger.warning(
                f"MongoDB connection attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} failed. Retrying in {RETRY_DELAY_SECONDS}s...")
            time.sleep(RETRY_DELAY_SECONDS)
    app.logger.error("Failed to connect to MongoDB after multiple retries. Grading service may not function.")


class GradeDocument(Resource):
    def post(self):
        data = request.get_json()
        if not data or 'document_id' not in data:
            return {'message': 'Missing document_id in request body'}, 400

        doc_id_str = data['document_id']
        try:
            doc_oid = ObjectId(doc_id_str)
        except Exception:
            return {'message': f'Invalid document_id format: {doc_id_str}'}, 400

        try:
            client = get_mongo_client()
            if not client:
                return {'message': 'MongoDB connection not available'}, 503

            db = client[MONGO_DB_NAME]
            collection = db[MONGO_COLLECTION_NAME]

            document = collection.find_one({"_id": doc_oid})
            if not document:
                return {'message': f'Document with ID {doc_id_str} not found'}, 404

            content_to_grade = document.get("content")
            if not content_to_grade:
                return {'message': f'No "content" field found in document {doc_id_str} or content is empty'}, 400

            original_filename = document.get("original_pdf_filename", "Unknown Document")

        except pymongo_errors.PyMongoError as e:
            app.logger.error(f"MongoDB error while fetching document {doc_id_str}: {e}")
            return {'message': f'MongoDB error: {e}'}, 500
        except Exception as e:
            app.logger.error(f"Unexpected error fetching document {doc_id_str}: {e}")
            return {'message': f'Unexpected error: {e}'}, 500

        prompt = (
            f"You are an AI grading assistant. Please evaluate the following text extracted from the document '{original_filename}'. "
            "Provide a numerical grade on a scale of 1 to 100, where 1 is the lowest and 100 is the highest. "
            "Also, provide a brief justification for your assessment. Consider aspects like clarity, correctness, "
            "completeness, and relevance to a typical academic context (assume a general one if not specified).\n\n"
            "Format your response starting with 'Numerical Grade: [score from 1-100]' followed by 'Justification: [your detailed justification]'.\n\n"
            "--- TEXT TO GRADE ---\n"
            f"{content_to_grade}\n"
            "--- END OF TEXT ---"
        )

        ollama_payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }

        try:
            app.logger.info(f"Sending content from document {doc_id_str} to Ollama model {OLLAMA_MODEL} for grading.")
            response = requests.post(f"{OLLAMA_API_BASE_URL}/api/generate", json=ollama_payload, timeout=120)
            response.raise_for_status()
            ollama_response_data = response.json()

            ai_evaluation = ollama_response_data.get("response", "No response text from AI.")

            app.logger.info(f"Received evaluation from Ollama for document {doc_id_str}.")
            return {
                'document_id': doc_id_str,
                'original_filename': original_filename,
                'evaluation_by_model': OLLAMA_MODEL,
                'evaluation_result': ai_evaluation,
                'ollama_full_response': ollama_response_data
            }, 200

        except requests.exceptions.Timeout:
            app.logger.error(f"Timeout connecting to Ollama for document {doc_id_str}")
            return {'message': 'Timeout connecting to Ollama grading service'}, 504
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Error connecting to Ollama for document {doc_id_str}: {e}")
            return {'message': f'Error communicating with Ollama AI service: {e}'}, 502
        except Exception as e:
            app.logger.error(f"Unexpected error during Ollama interaction for document {doc_id_str}: {e}")
            return {'message': f'Unexpected error during AI grading: {e}'}, 500


@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "message": "Grading service is running"}), 200


api.add_resource(GradeDocument, '/grade_document')

if __name__ == '__main__':
    init_db_connection()
    app.run(host='0.0.0.0', port=5002)