import argparse
import fitz  # PyMuPDF
from pymongo import MongoClient
import os
from datetime import datetime


def pdf_to_markdown(pdf_path):
    markdown_content = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text = page.get_text()
            markdown_content += text + "\n\n"
        return markdown_content.strip()
    except Exception as e:
        raise RuntimeError(f"PDF processing failed: {str(e)}")


def store_in_mongodb(data):
    try:
        client = MongoClient("mongodb://root:example@mongodb-server:27017/")
        db = client["Exams"]
        collection = db["pdf_submissions"]
        result = collection.insert_one(data)
        return result.inserted_id
    except Exception as e:
        raise RuntimeError(f"MongoDB operation failed: {str(e)}")


def main():
    parser = argparse.ArgumentParser(description="Upload PDF to MongoDB with metadata")

    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument("--username", required=True, help="Uploader's username (teacher/student)")
    parser.add_argument("--course", required=True, help="Course name")

    parser.add_argument("--student-name", required=True, help="Name of the student")
    parser.add_argument("--student-id", help="Student ID (optional)")

    parser.add_argument("--teacher", required=True, help="Teacher's username")
    parser.add_argument("--category", required=True,
                        choices=["question_paper", "answer_sheet", "reference_material"],
                        help="Type of document: question_paper, answer_sheet, or reference_material")

    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        raise FileNotFoundError(f"PDF file not found: {args.pdf}")

    try:
        markdown_content = pdf_to_markdown(args.pdf)
        submission_data = {
            "student_name": args.student_name,
            "student_id": args.student_id,  # Optional
            "uploader_username": args.username,
            "teacher_username": args.teacher,
            "course": args.course,
            "category": args.category,
            "content": markdown_content,
            "original_pdf": os.path.basename(args.pdf),
            "upload_time": datetime.utcnow()
        }

        inserted_id = store_in_mongodb(submission_data)
        print(f"Success! Submission ID: {inserted_id}")

    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)


if __name__ == "__main__":
    main()
