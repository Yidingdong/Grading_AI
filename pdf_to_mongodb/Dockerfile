FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pdf_to_mongodb.py .

CMD ["python", "pdf_to_mongodb.py"]