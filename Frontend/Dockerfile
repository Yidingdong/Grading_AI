FROM python:3.9-slim

WORKDIR /app

# Install curl for HEALTHCHECK instruction
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY ./Frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/utils/wait-for-it.sh /usr/local/bin/wait-for-it.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh

COPY ./Frontend/src /app/src
COPY ./Frontend/README.md /app/README.md

ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501
ENV PYTHONUNBUFFERED=1

ENV MYSQL_HOST=mysql-server
ENV MYSQL_USER=user
ENV MYSQL_PASSWORD=password
ENV MYSQL_DATABASE=Informations

ENV MONGO_HOST=mongodb-server
ENV MONGO_USER_FRONTEND=root
ENV MONGO_PASSWORD_FRONTEND=example
ENV MONGO_DB_NAME_FRONTEND=grading_ai_frontend
ENV MONGO_FILES_COLLECTION_FRONTEND=uploaded_material
# For frontend to call pdf processor
ENV PDF_PROCESSOR_URL=http://pdf-processor-service:5003

HEALTHCHECK --interval=20s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:${STREAMLIT_SERVER_PORT}/_stcore/health || exit 1

CMD ["/bin/sh", "-c", "echo 'Frontend service starting... Waiting for dependencies.' && wait-for-it.sh ${MYSQL_HOST}:${MYSQL_PORT:-3306} --timeout=60 --strict -- echo 'MySQL for Frontend is up.' && wait-for-it.sh ${MONGO_HOST}:${MONGO_PORT:-27017} --timeout=60 --strict -- echo 'MongoDB for Frontend is up.' && wait-for-it.sh pdf-processor-service:5003 --timeout=60 --strict -- echo 'PDF Processor for Frontend is up.' && echo 'All dependencies are up. Starting Streamlit application.' && streamlit run src/app.py --server.address=${STREAMLIT_SERVER_ADDRESS} --server.port=${STREAMLIT_SERVER_PORT} --server.enableCORS=false --server.enableXsrfProtection=false"]