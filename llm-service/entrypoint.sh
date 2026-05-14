#!/bin/bash
set -e

ollama serve &
OLLAMA_PID=$!

sleep 20

echo ">>> Pulling model ${LLM_MODEL}..."
ollama pull ${LLM_MODEL}

exec uvicorn main:app --host 0.0.0.0 --port 8000
