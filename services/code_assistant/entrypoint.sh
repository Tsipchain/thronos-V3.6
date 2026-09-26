#!/bin/bash
set -e

echo "=== Thronos Code Assistant ==="
echo "Starting Ollama server..."

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to initialize..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready."
        break
    fi
    sleep 2
done

# Pull the default model if not already available
MODEL="${OLLAMA_DEFAULT_MODEL:-qwen2.5-coder:32b}"
echo "Checking model: $MODEL"

if ! ollama list | grep -q "$MODEL"; then
    echo "Pulling model $MODEL (this may take a while on first run)..."
    ollama pull "$MODEL"
    echo "Model $MODEL ready."
else
    echo "Model $MODEL already available."
fi

# Start the Flask API
echo "Starting Code Assistant API on port 8080..."
cd /app
python3 -c "
from flask import Flask
from services.code_assistant.api_routes import code_assistant_bp

app = Flask(__name__)
app.register_blueprint(code_assistant_bp, url_prefix='/api/code-assistant')

@app.route('/health')
def health():
    return {'status': 'ok', 'service': 'thronos-code-assistant'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
" &
API_PID=$!

echo "=== Code Assistant Ready ==="
echo "  Ollama: http://localhost:11434"
echo "  API:    http://localhost:8080/api/code-assistant"
echo "  Model:  $MODEL"

# Wait for either process to exit
wait -n $OLLAMA_PID $API_PID
