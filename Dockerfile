# Portable production container for DataPulse Backend (Free-Tier / Docker-compatible)
# Consistent with render.yaml:
#   - Persistent metadata via external PostgreSQL (DATABASE_URL supplied at runtime)
#   - 30 packaged curated CSVs in data/curated/ + data/curated_manifest.json (no R2 required)
#   - Ephemeral DuckDB analytical cache in /tmp (re-hydrated on demand after restarts)
#   - Single Uvicorn worker (--workers 1) required for DuckDB single-writer lock safety
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    DUCKDB_PATH=/tmp/datapulse_analytics.duckdb \
    DATASETS_STORAGE_DIR=/tmp/datapulse_datasets \
    CURATED_MANIFEST_PATH=data/curated_manifest.json \
    CURATED_DATA_DIR=data/curated \
    CURATED_SYNC_ON_STARTUP=true \
    R2_REQUIRED_IN_PRODUCTION=true \
    EMBEDDINGS_ENABLED=false \
    AI_PROVIDER=groq \
    GROQ_MODEL=llama-3.3-70b-versatile

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data/curated_manifest.json ./data/curated_manifest.json
COPY data/curated ./data/curated

RUN mkdir -p /tmp/datapulse_datasets

EXPOSE 8000

# Single worker (--workers 1) is mandatory to preserve DuckDB single-writer lock safety
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
