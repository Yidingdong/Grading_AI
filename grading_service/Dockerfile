FROM python:3.9-slim

WORKDIR /app

COPY ./grading_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/utils/wait-for-it.sh /usr/local/bin/wait-for-it.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh

COPY ./grading_service/ .

ENV PYTHONUNBUFFERED=1

CMD ["python", "grading_service.py"]