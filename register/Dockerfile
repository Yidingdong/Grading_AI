FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY ./register/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/utils/wait-for-it.sh /usr/local/bin/wait-for-it.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh

COPY ./register/ .

CMD ["python", "register.py"]