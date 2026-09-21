# Optional single-container path. `make demo` on the host is faster and is what
# the runbook uses; this exists for a machine where installing Python 3.11 and
# Node is not worth the argument.
#
# Models are NOT baked into the image. They are downloaded once into a mounted
# volume, because a 1 GB image that rebuilds on every code change is worse than
# a small one plus a cache directory.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app/backend \
    HF_HUB_DISABLE_XET=1 \
    TOKENIZERS_PARALLELISM=false \
    BFSI_MODEL_DIR=/models \
    BFSI_RUNTIME_DIR=/runtime

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        -r backend/requirements.txt

COPY backend backend
COPY data data
COPY scripts scripts

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=90s \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", \
     "--host", "0.0.0.0", "--port", "8000"]
