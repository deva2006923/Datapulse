# Portable production container for DataPulse Backend (Railway / Render Docker / Fly.io)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATABASE_PATH=/var/data/datapulse.db \
    DUCKDB_PATH=/var/data/datapulse_analytics.duckdb \
    DATASETS_STORAGE_DIR=/var/data/datasets \
    EMBEDDINGS_ENABLED=false

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN mkdir -p /var/data/datasets

EXPOSE 8000

# Single worker (--workers 1) is mandatory to preserve DuckDB single-writer lock safety
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
