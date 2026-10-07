# DataPulse Backend

DataPulse is an intelligent data contribution, automated quality evaluation, and conversational query backend. It allows users to contribute structured CSV datasets, earn credits through automated schema validation, and perform cross-catalog natural language queries.

---

## Features
- **FastAPI Core**: High-performance asynchronous REST API with `redirect_slashes=False` to prevent Authorization header drops.
- **Dynamic CORS Engine**: Supports both explicit origin lists and regular expressions matching Lovable preview and production domains (`https://.*\\.(lovable\\.app|lovableproject\\.com|lovable\\.dev)$`).
- **Flexible Embeddings & Relevance**: Configurable `EMBEDDINGS_ENABLED` feature flag with lazy-loaded `sentence-transformers` and automatic TF-IDF/rule-based fallbacks.
- **Automated CSV Evaluation**: Evaluates schema fidelity, completeness, and domain relevance to award user credits.
- **Credit Redemption**: Allows users to redeem earned credits for cash payouts with schema and balance validation.
- **OpenAPI & Contract Documentation**: Automated export script generating `openapi.json` and human-readable `docs/API_CONTRACT.md`.

---

## Quickstart

### 1. Installation
Ensure Python 3.10+ is installed, then install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Environment Setup
Copy the example environment file:
```bash
cp .env.example .env
```

Key environment configurations:
- `CORS_ORIGINS`: Comma-separated list of allowed origins (e.g. `http://localhost:3000,http://localhost:5173,https://datapulse.ai.studio`).
- `CORS_ORIGIN_REGEX`: Regex pattern for preview domains (default: `https://.*\.(lovable\.app|lovableproject\.com|lovable\.dev)$`).
- `EMBEDDINGS_ENABLED`: `true` (uses dense embeddings) or `false` (uses TF-IDF only, fast startup, no heavy models loaded).

### 3. Run Development Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
or with Make:
```bash
make run
```

---

## Connecting a Lovable frontend

Follow these steps to connect your Lovable frontend (e.g., hosted on `https://datapulse.ai.studio` or a `*.lovable.app` / `*.lovableproject.com` preview domain) to this local backend:

### Step 1: Start Backend
Launch the backend server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Verify it is running locally at `http://localhost:8000/health`.

### Step 2: Start Tunnel
To expose your local backend over an HTTPS endpoint that Lovable can reach:
```bash
make tunnel
```
*(Or directly run: `cloudflared tunnel --url http://localhost:8000`)*.

### Step 3: Copy URL
Cloudflare Tunnel will output a public HTTPS URL like:
```
https://xxxx-xxxx-xxxx.trycloudflare.com
```
Copy this URL.

### Step 4: Set URL in Frontend Config
In your Lovable frontend project settings or `.env` configuration, set the API base URL:
```env
VITE_API_URL=https://xxxx-xxxx-xxxx.trycloudflare.com
```
*(If using the web editor, paste the URL in the Backend API / Environment Settings modal).*

### Step 5: Check `/health`
Verify that your frontend or browser can reach the backend tunnel:
```bash
curl https://xxxx-xxxx-xxxx.trycloudflare.com/health
```
Expected response:
```json
{
  "status": "ok",
  "cors_regex": true,
  "embeddings": true,
  "version": "1.0.0"
}
```

---

### Common Errors and Fixes

#### 1. CORS Error (`Access to fetch at ... has been blocked by CORS policy`)
- **Cause**: The origin of your Lovable frontend is neither in `CORS_ORIGINS` nor matching `CORS_ORIGIN_REGEX`.
- **Fix**: Check the origin in your browser's console (e.g., `https://preview--xxxx.lovable.app`). If using a custom domain, append it to `CORS_ORIGINS` in `.env`:
  ```env
  CORS_ORIGINS=http://localhost:3000,https://your-custom-domain.com
  ```
  Restart the backend server.

#### 2. Mixed Content Error (`The page at 'https://...' was loaded over HTTPS, but requested an insecure XMLHttpRequest endpoint 'http://...'`)
- **Cause**: The frontend is running over HTTPS (such as a Lovable preview domain) and trying to access `http://localhost:8000` directly. Browsers block plain HTTP calls from secure HTTPS origins.
- **Fix**: Always use the HTTPS Cloudflare Tunnel URL (`https://*.trycloudflare.com`) generated in Step 2 instead of `http://localhost:8000`.

#### 3. 401 Unauthorized (`Missing Authorization header` or `Invalid token`)
- **Cause**: Protected endpoints (such as `/datasets/upload`, `/me/stats`, `/credits/redeem`) require authentication, but no valid token was provided.
- **Fix**: Call `/auth/login` or `/auth/register` first, retrieve the `access_token`, and include it in your requests as:
  ```http
  Authorization: Bearer <token>
  ```
  *Note: Trailing slash redirects have been eliminated (`redirect_slashes=False`) so your Authorization header will never be stripped by automatic HTTP 307 redirects.*

#### 4. 402 Payment Required / Insufficient Balance
- **Cause**: Attempting to redeem credits or execute queries when your credit balance is insufficient.
- **Fix**: Upload more valid CSV datasets via `POST /datasets/upload`. The automated evaluation engine will evaluate your data and award you between 50 and 100 credits per dataset.

#### 5. 422 Unprocessable Entity
- **Cause**: The request body or uploaded file does not match the required schema (e.g. invalid JSON, missing CSV file, empty headers, or negative redeem amount).
- **Fix**: Consult `docs/API_CONTRACT.md` for exact payload schemas. For dataset uploads, ensure you are sending `multipart/form-data` with a valid `.csv` file.

---

## API Contract & Export

To re-export the OpenAPI specification and human-readable documentation:
```bash
python -m app.export_openapi
```
This generates:
- `openapi.json`: Machine-readable OpenAPI 3.1 specification.
- `docs/API_CONTRACT.md`: Complete human-readable contract with request/response models and error codes.

---

## Testing

### Run Unit and Integration Tests
```bash
pytest tests/ -v
```

### Run End-to-End Smoke Test
Make sure the server is running on `http://localhost:8000`, then run:
```bash
python scripts/smoke_test.py
```
Or target a remote or tunnel URL:
```bash
BASE_URL=https://your-tunnel-url.trycloudflare.com python scripts/smoke_test.py
```
