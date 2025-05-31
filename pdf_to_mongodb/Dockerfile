FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu curl && \
    rm -rf /var/lib/apt/lists/*

COPY ./pdf_to_mongodb/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/utils/wait-for-it.sh /usr/local/bin/wait-for-it.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh

COPY ./pdf_to_mongodb/pdfs /app/pdfs/
COPY ./pdf_to_mongodb/pdf_to_mongodb.py .

ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=pdf_to_mongodb.py

EXPOSE 5003

CMD ["/bin/sh", "-c", "wait-for-it.sh mongodb-server:27017 --timeout=60 --strict -- echo 'MongoDB for PDF Processor is up.' && python pdf_to_mongodb.py"]