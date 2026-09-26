# Thronos Code Assistant — Self-hosted GPU coding AI
# Runs Ollama + Qwen2.5-Coder on 24GB VRAM, no API key needed.
#
# Build:  docker build -t thronos-code-assistant -f services/code_assistant/Dockerfile .
# Run:    docker run --gpus all -p 11434:11434 -p 8080:8080 -v workspace:/app/workspace thronos-code-assistant

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV OLLAMA_HOST=0.0.0.0:11434
ENV OLLAMA_MODELS=/app/models
ENV CODE_ASSISTANT_WORKSPACE=/app/workspace
ENV CODE_ASSISTANT_SESSIONS=/app/data/code_sessions
ENV OLLAMA_BASE_URL=http://localhost:11434
ENV OLLAMA_DEFAULT_MODEL=qwen2.5-coder:32b

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Python dependencies
RUN pip3 install --no-cache-dir flask gunicorn

# Create directories
RUN mkdir -p /app/models /app/workspace /app/data/code_sessions /app/logs

WORKDIR /app

# Copy application code
COPY ai/ /app/ai/
COPY services/code_assistant/ /app/services/code_assistant/

# Entry script: start Ollama, pull model, start Flask API
COPY services/code_assistant/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 11434 8080

VOLUME ["/app/models", "/app/workspace", "/app/data"]

CMD ["/app/entrypoint.sh"]
