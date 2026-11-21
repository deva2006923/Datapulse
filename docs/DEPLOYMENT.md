# DataPulse Production Deployment Guide

This guide covers deploying **DataPulse** to production using:
- **Frontend:** Vercel (`frontend/` root directory, React + Vite + TypeScript + Bun)
- **Backend:** Render (or Railway) running FastAPI + Uvicorn with a **persistent disk/volume**
- **Source Control:** GitHub (`https://github.com/deva2006923/Datapulse`, branch `main`)
- **Custom Domain (optional):** `datapulse.ai.studio`

---

## 1. Architecture & Persistent Storage Layout

DataPulse stores stateful data in three places that **MUST live on a persistent disk/volume** (never an ephemeral container filesystem):

| Data Asset | Environment Variable | Production Mount Path | Persisted Contents |
| --- | --- | --- | --- |
| SQLite Metadata DB | `DATABASE_PATH` | `/var/data/datapulse.db` | Users, password hashes, credit balances, credit transactions, dataset metadata, evaluations, query history, dataset versions, dataset unlocks, admin audit logs |
| DuckDB Analytical DB | `DUCKDB_PATH` | `/var/data/datapulse_analytics.duckdb` | Uploaded dataset analytical tables (`dataset_ds_*`) and `_dataset_registry` |
| Uploaded CSV Files | `DATASETS_STORAGE_DIR` | `/var/data/datasets` | Original sanitized CSV files (`ds_*.csv`) |

### Critical Runtime Rules
1. **Single Uvicorn Worker (`--workers 1`)**: DuckDB enforces a single-process file write lock. Running multiple Uvicorn worker processes against `/var/data/datapulse_analytics.duckdb` will cause `IO Error: Cannot open file ... being used by another process`. Always keep `--workers 1` (already configured in `render.yaml` and `Dockerfile`).
2. **SQLite WAL Mode**: `app/database.py` automatically enables `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=15000`, and `timeout=30.0`, and safely creates parent directories (`os.makedirs(..., exist_ok=True)`) on startup without overwriting existing databases.
3. **Upload Limit**: `MAX_UPLOAD_SIZE_MB=25` rejects oversized CSV uploads with HTTP `413` before ingestion.

---

## 2. Free Tier vs Paid Production Requirements

| Requirement | Render Free Tier | Render Starter (~$7/mo) + Disk (~$2.50/mo for 10GB) | Railway Hobby (~$5/mo) + Volume | Vercel Hobby (Free) |
| --- | --- | --- | --- | --- |
| Persistent Disk / Volume | **NOT supported** (data wiped on every restart/redeploy!) | **Supported** (`/var/data` persists across deploys) | **Supported** (`/var/data` volume persists) | N/A (static SPA) |
| Cold-Start Sleep | Sleeps after 15m inactivity (~30–60s wake time) | Always-on (no sleep) | Always-on | Instant edge CDN |
| Custom HTTPS Domain | Supported | Supported | Supported | Supported (free SSL) |
| Recommended for Production? | **No — will lose all user data & uploads** | **Yes (Recommended)** | **Yes (Alternative)** | **Yes (Frontend)** |

> **Warning:** Never deploy the DataPulse backend to an ephemeral free-tier instance without a mounted persistent volume—every redeploy or container restart will erase `datapulse.db`, `datapulse_analytics.duckdb`, and all uploaded CSVs.

---

## 3. Pre-Deployment Security Checklist

Before creating the production backend service:

1. **Rotate the previously exposed Gemini API key**
   - Go to Google AI Studio -> API Keys, revoke the old development key, and generate a brand-new production key.
   - Store the new key **ONLY** in the Render/Railway backend `GEMINI_API_KEY` environment variable (never in Vercel or GitHub).
2. **Generate a strong `SECRET_KEY`**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   (On Render Blueprint, `generateValue: true` generates one automatically.)
3. **Restrict Production CORS**
   - Set `CORS_ORIGINS` strictly to your deployed frontend origin(s), e.g.:
     ```env
     CORS_ORIGINS=https://datapulse.ai.studio,https://your-project.vercel.app
     ```
   - Leave `CORS_ORIGIN_REGEX` empty (`""`) in production unless preview subdomains are explicitly required.
4. **Admin Security**
   - Keep `ADMIN_EMAIL=datapulseapplication@gmail.com`.
   - Public `/auth/register` always creates `is_admin = 0`; admin privileges can only be granted via `scripts/init_admin.py` executed directly against the production database.

---

## 4. Backend Deployment (Render — Recommended)

### Option A: Deploy via `render.yaml` Blueprint (Fastest)
1. Push your `main` branch to GitHub (`https://github.com/deva2006923/Datapulse`).
2. In the **Render Dashboard**, click **New + -> Blueprint**.
3. Connect `deva2006923/Datapulse` and select branch `main`.
4. Render automatically reads `render.yaml`, creating:
   - Service: `datapulse-backend` (Python 3.11.9, Starter plan)
   - Persistent Disk: `datapulse-persistent-data` mounted at `/var/data` (10 GB)
   - Build command: `pip install --upgrade pip && pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips="*"`
   - Health check path: `/health`
5. When prompted for `GEMINI_API_KEY` (`sync: false`), paste your **rotated** Gemini API key.
6. Update `CORS_ORIGINS` to include both your Vercel URL (`https://<project>.vercel.app`) and `https://datapulse.ai.studio`.
7. Click **Apply** and wait for the deploy to become **Live**.

### Option B: Railway (Docker Alternative)
1. In Railway, click **New Project -> Deploy from GitHub repo** (`deva2006923/Datapulse`).
2. Railway automatically detects the root `Dockerfile`.
3. Attach a **Volume** mounted at `/var/data`.
4. Set environment variables:
   - `ENVIRONMENT=production`
   - `DATABASE_PATH=/var/data/datapulse.db`
   - `DUCKDB_PATH=/var/data/datapulse_analytics.duckdb`
   - `DATASETS_STORAGE_DIR=/var/data/datasets`
   - `EMBEDDINGS_ENABLED=false`
   - `ADMIN_EMAIL=datapulseapplication@gmail.com`
   - `CORS_ORIGINS=https://datapulse.ai.studio,https://<your-vercel-app>.vercel.app`
   - `CORS_ORIGIN_REGEX=`
   - `SECRET_KEY=<generated-64-char-random-key>`
   - `GEMINI_API_KEY=<rotated-gemini-api-key>`
   - `GEMINI_MODEL=gemini-2.5-flash`
5. Generate a public Railway HTTPS domain and verify `/health`.

### Verify Backend Health
```bash
curl https://<your-backend-domain>/health
```
Expected HTTP `200 OK`:
```json
{
  "status": "ok",
  "cors_regex": false,
  "embeddings": false,
  "version": "1.0.0",
  "database_ok": true,
  "storage_ok": true,
  "environment": "production"
}
```

---

## 5. Production Administrator Initialization

> **CRITICAL:** Local development databases are never uploaded to production. You must initialize the administrator directly on the live production persistent volume.

1. Open the **Render Shell** (or `railway run bash`) for `datapulse-backend`.
2. Confirm persistent env vars point to `/var/data`:
   ```bash
   echo "$DATABASE_PATH"   # Must output: /var/data/datapulse.db
   ```
3. Run the secure bootstrap script (prompts interactively for password without echoing it to shell history):
   ```bash
   python scripts/init_admin.py --email datapulseapplication@gmail.com
   ```
   Or if promoting an already-registered production account without changing its password:
   ```bash
   python scripts/init_admin.py --email datapulseapplication@gmail.com --promote
   ```
4. Verify output confirms:
   `Administrative status verified: is_admin = 1`

Never hardcode admin passwords in `render.yaml`, `Dockerfile`, scripts, or GitHub.

---

## 6. Frontend Deployment (Vercel)

1. In the **Vercel Dashboard**, click **Add New... -> Project** and import `deva2006923/Datapulse`.
2. Configure Project Settings:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite (auto-detected from `frontend/vercel.json`)
   - **Install Command:** `bun install`
   - **Build Command:** `bun run build`
   - **Output Directory:** `dist`
3. Add the **Environment Variable** (Production & Preview):
   - `VITE_API_URL` = `https://<your-backend-domain>` (e.g. `https://datapulse-backend.onrender.com` — **HTTPS only, no trailing slash, no localhost**)
   - **Do NOT add** `GEMINI_API_KEY` or `SECRET_KEY` to Vercel!
4. Click **Deploy**.
5. Once Vercel assigns `https://<your-project>.vercel.app`, add that exact URL to `CORS_ORIGINS` on Render and redeploy/restart the backend.

### Connecting Custom Domain (`datapulse.ai.studio`)
1. In Vercel -> Project -> **Settings -> Domains**, add `datapulse.ai.studio`.
2. In your DNS registrar for `ai.studio` (or `datapulse.ai.studio`), configure the exact DNS record Vercel provides:
   - Subdomain (`datapulse.ai.studio`): `CNAME` record pointing to `cname.vercel-dns.com`
3. Wait for Vercel to verify DNS and auto-issue the TLS/SSL certificate.
4. Confirm `https://datapulse.ai.studio` is listed in Render's `CORS_ORIGINS`.

---

## 7. Backup, Restoration & Safe Deployment Procedure

### Manual / Scheduled Backup (from Render/Railway Shell)
Use SQLite's online `.backup` API (safe even while live traffic is writing in WAL mode):
```bash
mkdir -p /var/data/backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
python -c "
import sqlite3
src = sqlite3.connect('/var/data/datapulse.db')
dst = sqlite3.connect(f'/var/data/backups/datapulse_${STAMP}.db')
src.backup(dst)
dst.close(); src.close()
"
tar -czf /var/data/backups/datapulse_full_${STAMP}.tar.gz \
  /var/data/backups/datapulse_${STAMP}.db \
  /var/data/datapulse_analytics.duckdb \
  /var/data/datasets
```
Copy backups off-host periodically (e.g. S3/GCS bucket or secure download) for disaster recovery.

### Safe Restoration Procedure
1. Suspend / stop the backend service so no process holds locks on SQLite or DuckDB.
2. Restore `datapulse.db`, `datapulse_analytics.duckdb`, and `/var/data/datasets/*` into `/var/data/`.
3. Remove stale `-wal`/`-shm` files if restoring a cold SQLite snapshot (`rm -f /var/data/datapulse.db-wal /var/data/datapulse.db-shm`).
4. Start the backend service and verify `GET /health` returns `database_ok: true` and `storage_ok: true`.

### Safe Redeployment & Schema Migration Procedure
- `app/database.py` runs idempotent `CREATE TABLE IF NOT EXISTS` and additive `_run_safe_migrations()` on startup — it **never** drops tables or deletes existing production records.
- Always back up `/var/data` before deploying schema changes.

---

## 8. Live Production Verification Checklist

After both Render and Vercel finish deploying, verify every flow against the live HTTPS URLs:

1. **Frontend HTTPS load**: Open `https://datapulse.ai.studio` (or `https://<project>.vercel.app`) — zero console errors, zero mixed-content warnings, SPA route refreshes work without 404.
2. **Backend Health**: `curl https://<backend-url>/health` returns HTTP `200` with `database_ok: true`, `storage_ok: true`, `environment: "production"`.
3. **CORS Enforcement**: Requests from the production frontend succeed; unauthorized origins are rejected.
4. **Auth & Registration**: Register a regular user -> receives 100 initial credits, `is_admin: false`, and gets HTTP `403` on `/admin/overview`.
5. **Dataset Upload & Evaluation**: Upload a valid `.csv` -> persisted to `/var/data/datasets/`, ingested into `/var/data/datapulse_analytics.duckdb`, credits awarded; oversized (>25MB) or non-CSV files rejected cleanly (`413` / `400`).
6. **Marketplace & Search**: Dataset appears in catalog and semantic/TF-IDF search.
7. **Natural-Language Query & DuckDB Execution**: Run a question on an uploaded dataset -> Gemini generates SELECT-only SQL, DuckDB returns real rows, query history persists, and credits/fees update accurately.
8. **Admin Control Center**: Log in as `datapulseapplication@gmail.com` -> `/admin` loads all 7 tabs, analytics charts, user history drawer, dataset inspector, and credit ledger without leaking secrets or raw CSV rows.
9. **Persistence Across Restart**: Restart the Render backend service -> confirm registered users, credit balances, uploaded datasets, DuckDB tables, and query history are all still intact.
10. **Automated Smoke Test**:
    ```bash
    BASE_URL=https://<your-backend-domain> python scripts/smoke_test.py
    ```
