# DataPulse — Production Storage, AI Fallback & Migration Guide

This document describes the production-ready storage architecture (**PostgreSQL + Cloudflare R2 + DuckDB cache**) and **Gemini + Groq AI fallback** setup, while keeping local development 100% compatible with SQLite + DuckDB.

---

## 1. Architecture Overview

| Data Layer | Local Development | Production (Render + Cloudflare) |
|---|---|---|
| **Transactional Metadata** (users, auth tokens, datasets, evaluations, credit balances, credit transactions, query history, unlocks, versions, admin audit logs) | SQLite (`DATABASE_PATH=datapulse.db`) | Managed PostgreSQL (`DATABASE_URL=postgresql://...`) |
| **Persistent CSV Files** (uploaded community CSVs & curated library CSVs) | Local disk (`storage/datasets/`) | Cloudflare R2 (`community/<id>/<sha256>.csv.gz` & `curated/<id>/<ver>/<sha256>.csv.gz`) |
| **Analytical Query Engine** | DuckDB (`datapulse_analytics.duckdb`) | Ephemeral/mounted DuckDB with automatic SHA-256-verified on-demand R2 re-hydration |
| **NL-to-SQL AI Engine** | Gemini primary + Groq fallback | Gemini primary (`gemini-2.5-flash`) + Groq fallback (`llama-3.3-70b-versatile` with automatic backup model failover) |

---

## 2. Manual Infrastructure Setup Steps

### A. Provision Managed PostgreSQL (Render / Neon / Supabase)
1. Create a PostgreSQL instance in your chosen region (e.g., Render Postgres in `oregon` matching your backend service).
2. Copy the **Internal Database URL** (or External SSL URL with `?sslmode=require`).
3. Set `DATABASE_URL` in Render Backend → **Environment Variables**.
   - Leave `DATABASE_URL` unset locally to continue using SQLite (`datapulse.db`).

### B. Provision Cloudflare R2 Object Storage
1. In Cloudflare Dashboard → **R2 Object Storage**, create a private bucket (e.g., `datapulse-datasets-prod`).
2. Create an **R2 API Token** with **Object Read & Write** permissions scoped strictly to that bucket.
3. Configure these Render Backend environment variables:
   - `R2_ENDPOINT_URL=https://<cloudflare_account_id>.r2.cloudflarestorage.com`
   - `R2_BUCKET_NAME=datapulse-datasets-prod`
   - `R2_ACCESS_KEY_ID=<r2_access_key_id>`
   - `R2_SECRET_ACCESS_KEY=<r2_secret_access_key>`
   - `R2_REGION=auto`
   - `R2_PERSIST_COMMUNITY_UPLOADS=true`
   - `R2_REQUIRED_IN_PRODUCTION=true` *(recommended once R2 is provisioned so uploads never silently fall back to ephemeral disk)*

### C. Configure Gemini + Groq AI Providers (Render & Local `.env`)
- `AI_PROVIDER=gemini`
- `GEMINI_API_KEY=<your_gemini_api_key>`
- `GEMINI_MODEL=gemini-2.5-flash`
- `AI_FALLBACK_PROVIDER=groq`
- `GROQ_API_KEY=<your_groq_api_key>`
- `GROQ_MODEL=llama-3.3-70b-versatile`
- `GROQ_BACKUP_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b`

---

## 3. Migrating Existing SQLite Data to PostgreSQL (+ R2)

1. **Dry-run first (read-only against SQLite, zero writes to PostgreSQL/R2):**
   ```powershell
   .\.venv\Scripts\python.exe scripts/migrate_sqlite_to_postgres.py `
     --sqlite-path datapulse.db `
     --postgres-url "$env:DATABASE_URL" `
     --dry-run
   ```
2. **Execute non-destructive migration (preserves existing records via `ON CONFLICT DO NOTHING`):**
   ```powershell
   .\.venv\Scripts\python.exe scripts/migrate_sqlite_to_postgres.py `
     --sqlite-path datapulse.db `
     --postgres-url "$env:DATABASE_URL" `
     --execute `
     --upload-r2
   ```
3. Verify `source_counts == target_counts` and `source_total_credits == target_total_credits` in the output JSON.

---

## 4. Ingesting Verified Curated Datasets into Cloudflare R2

1. **Audit license & metadata eligibility (171 verified entries, 79 unverified excluded):**
   ```powershell
   .\.venv\Scripts\python.exe scripts/ingest_curated_datasets.py --dry-run
   ```
2. **Ingest verified datasets to R2 and update metadata DB (start with a small batch first):**
   ```powershell
   .\.venv\Scripts\python.exe scripts/ingest_curated_datasets.py `
     --upload-r2 `
     --limit 10 `
     --report-out curated_ingestion_report.json
   ```
3. Only entries with `ingestion_status = 'ingested'`, valid `object_storage_key`, and valid `sha256_checksum` become visible and queryable (for `0` credits) in the Marketplace and Query Workspace.

