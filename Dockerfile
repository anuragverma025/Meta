# ──────────────────────────────────────────────────────────────────────────────
# Dockerfile — CodeReview-Env (HuggingFace Spaces compatible)
# Must be at the repository root for HF Spaces to pick it up.
# Build: docker build -t codereview-env .
# Run:   docker run -p 7860:7860 -e HF_TOKEN=hf_xxx codereview-env
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System essentials
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies first (maximise Docker layer caching) ────────
COPY server/requirements.txt requirements.txt
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

# ── Copy project source ───────────────────────────────────────────────────────
COPY . .

# ── Install the codereview_env package (editable) ─────────────────────────────
RUN pip install --no-cache-dir -e .

# ── Environment defaults ───────────────────────────────────────────────────────
ENV PORT=7860
ENV HOST=0.0.0.0
ENV HF_DATASETS_CACHE=/app/.cache/datasets
ENV PYTHONUNBUFFERED=1

# ── Expose and start ──────────────────────────────────────────────────────────
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
