#!/bin/sh
set -e

/bin/ollama serve &
pid=$!
echo "Ollama server process started with PID $pid"

echo "Waiting for Ollama server to be available at http://localhost:11434..."
max_retries=30
count=0
while ! curl -s -f http://localhost:11434/api/tags > /dev/null; do
    sleep 2
    count=$((count + 1))
    if [ ${count} -ge ${max_retries} ]; then
        echo "Ollama server failed to start or become responsive after ${max_retries} retries."
        kill $pid
        exit 1
    fi
    echo -n "."
done
echo "\nOllama server is ready."

MODEL_NAME="granite3.2-vision:latest"
echo "Attempting to pull model: $MODEL_NAME ..."
if /bin/ollama pull "$MODEL_NAME"; then
    echo "Model $MODEL_NAME pulled successfully or already exists."
else
    echo "WARNING: Failed to pull model $MODEL_NAME."
    echo "This could be because the model name is incorrect, it's not available on the Ollama Hub, or a network issue."
    echo "The Ollama server will continue to run. You can try pulling another model manually via 'docker exec ollama-ai-server ollama pull <model_name>'."
fi

echo "Ollama setup complete. Server is running."
wait $pid
echo "Ollama server process $pid exited."