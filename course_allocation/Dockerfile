FROM python:3.9-slim

WORKDIR /app
COPY ./course_allocation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./scripts/wait-for-it.sh /usr/local/bin/wait-for-it.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh
COPY ./course_allocation/ .

CMD ["python", "course_allocation.py"]