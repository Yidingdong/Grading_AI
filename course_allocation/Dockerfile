FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY ./course_allocation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/utils/wait-for-it.sh /usr/local/bin/wait-for-it.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh
COPY ./course_allocation/ .

CMD ["python", "course_allocation.py"]