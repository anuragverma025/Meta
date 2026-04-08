FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (Docker layer caching)
COPY server/requirements.txt .
RUN pip install --upgrade pip
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Install the codereview_env package
RUN pip install -e .

# Environment configuration
ENV ENABLE_WEB_INTERFACE=true
ENV PORT=7860
ENV HOST=0.0.0.0
ENV HF_DATASETS_CACHE=/app/.cache/datasets

EXPOSE 7860

# Health check so HuggingFace knows the container is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:7860/health || exit 1

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
