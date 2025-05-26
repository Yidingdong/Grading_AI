import argparse
import fitz
from pymongo import MongoClient
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def pdf_to_markdown(pdf_path, ocr_threshold=20, language="eng", ocr_dpi=300):
    markdown_content = ""
    doc = None
    try:
        doc = fitz.open(pdf_path)
        logger.info(f"Processing PDF: {pdf_path} with {len(doc)} pages. OCR DPI set to: {ocr_dpi}, Lang: {language}")

        for i, page in enumerate(doc):
            page_num = i + 1
            logger.info(f" Processing page {page_num}...")

            text = page.get_text("text")
            extracted_text = text.strip() if text else ""

            if len(extracted_text) < ocr_threshold:
                logger.info(f"  Page {page_num}: Standard text extraction minimal ({len(extracted_text)} chars). Attempting OCR (lang={language}, dpi={ocr_dpi}, flags=3)...")
                try:
                    tp_ocr = page.get_textpage_ocr(language=language, dpi=ocr_dpi, flags=3, full=True)
                    if tp_ocr:
                        ocr_text = page.get_text("text", textpage=tp_ocr)
                        extracted_text = ocr_text.strip() if ocr_text else ""
                        logger.info(f"  Page {page_num}: OCR successful ({len(extracted_text)} chars).")
                    else:
                        logger.info(f"  Page {page_num}: OCR TextPage generation failed (returned None).")
                        extracted_text = ""

                except RuntimeError as rt_err:
                     logger.error(f"  Page {page_num}: OCR attempt failed with RuntimeError: {rt_err}")
                     if "tesseract" in str(rt_err).lower():
                         logger.info(f"  Hint: Ensure Tesseract OCR engine and language data ('{language}') are correctly installed in the container.")
                     extracted_text = ""
                except Exception as ocr_error:
                     logger.error(f"  Page {page_num}: OCR attempt failed with unexpected error: {type(ocr_error).__name__} - {ocr_error}")
                     extracted_text = ""
            else:
                logger.info(f"  Page {page_num}: Standard text extraction successful ({len(extracted_text)} chars).")

            markdown_content += extracted_text + "\n\n"

        return markdown_content.strip()

    except Exception as e:
        logger.error(f"PDF processing failed for {pdf_path}: {str(e)}")
        raise RuntimeError(f"PDF processing failed for {pdf_path}: {str(e)}")
    finally:
        if doc:
            doc.close()
            logger.info(f"Closed PDF document: {pdf_path}")


def store_in_mongodb(data):
    client = None
    try:
        client = MongoClient("mongodb://root:example@mongodb-server:27017/")
        client.admin.command('ping')
        logger.info("MongoDB connection successful.")

        db = client["Exams"]
        collection = db["pdf_submissions"]
        logger.info(f"Storing data to MongoDB (Collection: {collection.name})...")
        result = collection.insert_one(data)
        logger.info(f"Data stored successfully. Inserted ID: {result.inserted_id}")
        return result.inserted_id
    except Exception as e:
        logger.error(f"MongoDB operation failed: {str(e)}")
        raise RuntimeError(f"MongoDB operation failed: {str(e)}")
    finally:
        if client:
            client.close()
            logger.info("MongoDB connection closed.")


def main():
    parser = argparse.ArgumentParser(description="Extract text/OCR PDF and upload to MongoDB with metadata")

    parser.add_argument("--pdf", required=True, help="Path to PDF file inside the container (e.g., /app/pdfs/yourfile.pdf)")
    parser.add_argument("--username", required=True, help="Uploader's username (teacher/student)")
    parser.add_argument("--course", required=True, help="Course name")
    parser.add_argument("--student-name", required=True, help="Name of the student")
    parser.add_argument("--student-id", help="Student ID (optional)")
    parser.add_argument("--teacher", required=True, help="Teacher's username")
    parser.add_argument("--category", required=True,
                        choices=["question_paper", "answer_sheet", "reference_material"],
                        help="Type of document: question_paper, answer_sheet, or reference_material")
    parser.add_argument("--lang", default="eng", help="Tesseract language for OCR (e.g., eng, deu). Default: eng")
    parser.add_argument("--ocr-threshold", type=int, default=20,
                        help="Character count threshold below which OCR will be attempted. Default: 20")
    parser.add_argument("--ocr-dpi", type=int, default=300,
                        help="DPI for OCR image rendering. Higher values may improve accuracy but increase processing time. Default: 300")


    args = parser.parse_args()

    logger.info(f"--- Starting PDF Processing ---")
    logger.info(f" Arguments: {vars(args)}")


    if not os.path.exists(args.pdf):
        logger.error(f"Input PDF file not found inside the container: {args.pdf}")
        raise FileNotFoundError(f"Input PDF file not found inside the container: {args.pdf}")

    try:
        markdown_content = pdf_to_markdown(
            pdf_path=args.pdf,
            ocr_threshold=args.ocr_threshold,
            language=args.lang,
            ocr_dpi=args.ocr_dpi
        )

        if not markdown_content:
             logger.warning(f"Warning: Extracted content is empty after processing {args.pdf}.")

        submission_data = {
            "student_name": args.student_name,
            "student_id": args.student_id if args.student_id else None,
            "uploader_username": args.username,
            "teacher_username": args.teacher,
            "course": args.course,
            "category": args.category,
            "content": markdown_content,
            "original_pdf_filename": os.path.basename(args.pdf),
            "upload_time": datetime.utcnow()
        }

        inserted_id = store_in_mongodb(submission_data)
        logger.info(f"\n--- Success! ---")
        logger.info(f" PDF processed and data stored in MongoDB.")
        logger.info(f" Submission ID: {inserted_id}")

    except FileNotFoundError as fnf_err:
        logger.error(f"\n!!! Error: {str(fnf_err)} !!!")
        logger.error(f"!!! Please ensure the file exists at the specified path inside the 'pdf-uploader' container. Check volume mounts in docker-compose.yml. !!!")
        exit(1)
    except RuntimeError as run_err:
        logger.error(f"\n!!! Runtime Error during processing: {str(run_err)} !!!")
        exit(1)
    except Exception as e:
        logger.error(f"\n!!! An unexpected error occurred: {type(e).__name__} - {str(e)} !!!")
        exit(1)

if __name__ == "__main__":
    main()