"""
Tests for Gemini API HTTP 429 quota handling, exponential backoff,
configurable fallback AI provider, secret-redacted backend logging,
zero credit deduction, and non-fabrication guarantees.
"""

import io
import logging
import uuid
from unittest.mock import MagicMock, patch

import httpx
from google.genai import errors as genai_errors

from app.config import settings
from app.database import get_db_connection
from app.services.nl_query import AI_QUOTA_USER_MESSAGE, AI_UNAVAILABLE_USER_MESSAGE, _redact_secrets
from app.services.storage import get_dataset_table_name


def _register(client, prefix="quota"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"User {prefix}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return {
        "user_id": data["user"]["id"],
        "email": email,
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _upload_public_dataset(client, owner_headers, name="Quota Test Sales"):
    csv_text = "item,category,revenue\nLaptop,Tech,1200\nDesk,Office,450\nChair,Office,300\n"
    res = client.post(
        "/datasets/upload",
        headers=owner_headers,
        files={"file": ("quota_sales.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
        data={"name": name, "domain": "retail", "visibility": "public"},
    )
    assert res.status_code == 201, res.text
    ds = res.json()
    return ds["id"], get_dataset_table_name(ds["id"])


def _credits(client, headers):
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200
    return res.json()["credits"]


def _tx_count(user_ids):
    conn = get_db_connection()
    placeholders = ",".join("?" for _ in user_ids)
    return conn.execute(
        f"SELECT COUNT(*) FROM credit_transactions WHERE user_id IN ({placeholders})",
        tuple(user_ids),
    ).fetchone()[0]


def test_gemini_429_hard_quota_no_retry_safe_message_zero_credits_and_secure_logging(client, caplog):
    owner = _register(client, "q429_owner")
    buyer = _register(client, "q429_buyer")
    ds_id, _ = _upload_public_dataset(client, owner["headers"])

    buyer_before = _credits(client, buyer["headers"])
    owner_before = _credits(client, owner["headers"])
    tx_before = _tx_count([buyer["user_id"], owner["user_id"]])

    fake_secret_key = "AIzaSyFakeSecretKeyValue1234567890ABCDEF"
    raw_gemini_429 = genai_errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "message": (
                    f"You exceeded your current quota, please check your plan and billing details. "
                    f"Quota exceeded for metric: GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 0 "
                    f"(key={fake_secret_key})"
                ),
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )

    sleep_calls = []
    call_count = 0

    def _failing_gemini(api_key, model_name, prompt):
        nonlocal call_count
        call_count += 1
        raise raw_gemini_429

    with caplog.at_level(logging.WARNING, logger="app.services.nl_query"), patch.object(
        settings, "AI_PROVIDER", "gemini"
    ), patch.object(settings, "GEMINI_API_KEY", fake_secret_key), patch.object(
        settings, "AI_FALLBACK_PROVIDER", None
    ), patch.object(settings, "AI_FALLBACK_API_KEY", None), patch.object(
        settings, "AI_MAX_RETRIES", 2
    ), patch("app.services.nl_query._call_gemini_once", side_effect=_failing_gemini), patch(
        "app.services.nl_query._sleep", side_effect=lambda s: sleep_calls.append(s)
    ):
        # Even for a prompt that contains "how many rows", Gemini 429 MUST NOT fabricate/fallback-rule SQL!
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "How many rows are in this dataset?", "dataset_id": ds_id},
        )

    assert res.status_code == 503
    detail = res.json()["detail"]
    assert detail == AI_QUOTA_USER_MESSAGE

    # Verify technical internals & secrets are completely hidden from API response
    for forbidden in ("RESOURCE_EXHAUSTED", "429", "GenerateRequestsPerDay", "billing", fake_secret_key, "AIza"):
        assert forbidden not in detail

    # Hard/daily quota exhaustion must NOT retry
    assert call_count == 1
    assert sleep_calls == []

    # Credits and ledger transactions must remain 100% untouched
    assert _credits(client, buyer["headers"]) == buyer_before
    assert _credits(client, owner["headers"]) == owner_before
    assert _tx_count([buyer["user_id"], owner["user_id"]]) == tx_before

    # Query history must also store only the safe user message, never raw error or secret
    hist = client.get("/query/history", headers=buyer["headers"]).json()
    assert len(hist["items"]) >= 1
    latest = hist["items"][0]
    assert latest["credits_charged"] == 0
    assert latest["rows_returned"] == 0
    assert latest["error_message"] == AI_QUOTA_USER_MESSAGE
    assert fake_secret_key not in (latest["error_message"] or "")

    # Backend log must contain detailed structured diagnostic WITH secret redacted
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "HTTP 429" in log_text
    assert "hard_quota_exhausted" in log_text
    assert fake_secret_key not in log_text
    assert "[REDACTED" in log_text


def test_gemini_429_transient_rate_limit_retries_with_exponential_backoff_and_recovers(client):
    owner = _register(client, "qretry_owner")
    buyer = _register(client, "qretry_buyer")
    ds_id, table_name = _upload_public_dataset(client, owner["headers"], name="Transient Retry Sales")

    buyer_before = _credits(client, buyer["headers"])
    owner_before = _credits(client, owner["headers"])

    transient_429 = genai_errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "message": "Too Many Requests: transient burst rate limit exceeded.",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )

    sleep_calls = []
    attempts = 0

    def _flaky_gemini(api_key, model_name, prompt):
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise transient_429
        return f"SELECT SUM(revenue) AS total_rev FROM {table_name}"

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "test-gemini-key-123456"
    ), patch.object(settings, "AI_FALLBACK_PROVIDER", None), patch.object(
        settings, "AI_MAX_RETRIES", 2
    ), patch.object(settings, "AI_RETRY_BASE_DELAY_SECONDS", 0.5), patch.object(
        settings, "AI_RETRY_MAX_WAIT_SECONDS", 4.0
    ), patch("app.services.nl_query._call_gemini_once", side_effect=_flaky_gemini), patch(
        "app.services.nl_query._sleep", side_effect=lambda s: sleep_calls.append(s)
    ):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "What is the total revenue?", "dataset_id": ds_id},
        )

    assert res.status_code == 200, res.text
    data = res.json()
    assert attempts == 3
    assert len(sleep_calls) == 2
    # Exponential backoff: 2nd sleep >= 1st sleep (0.5..0.6 vs 1.0..1.2), both <= max_wait
    assert 0.5 <= sleep_calls[0] <= 0.75
    assert 1.0 <= sleep_calls[1] <= 1.25
    assert data["results"][0]["total_rev"] == 1950
    assert data["credits_charged"] == 1
    assert _credits(client, buyer["headers"]) == buyer_before - 1
    assert _credits(client, owner["headers"]) == owner_before + 1


def test_gemini_429_long_retry_delay_skips_retry_and_preserves_credits(client):
    owner = _register(client, "qlong_owner")
    buyer = _register(client, "qlong_buyer")
    ds_id, _ = _upload_public_dataset(client, owner["headers"], name="Long Retry Delay Sales")

    buyer_before = _credits(client, buyer["headers"])
    long_delay_429 = genai_errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "message": "Rate limit hit. Please retry in 45s.",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )

    sleep_calls = []
    attempts = 0

    def _long_delay_call(api_key, model_name, prompt):
        nonlocal attempts
        attempts += 1
        raise long_delay_429

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "test-gemini-key-123456"
    ), patch.object(settings, "AI_FALLBACK_PROVIDER", None), patch.object(
        settings, "AI_MAX_RETRIES", 2
    ), patch.object(settings, "AI_RETRY_MAX_WAIT_SECONDS", 4.0), patch(
        "app.services.nl_query._call_gemini_once", side_effect=_long_delay_call
    ), patch("app.services.nl_query._sleep", side_effect=lambda s: sleep_calls.append(s)):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Revenue breakdown by category", "dataset_id": ds_id},
        )

    assert res.status_code == 503
    assert res.json()["detail"] == AI_QUOTA_USER_MESSAGE
    assert attempts == 1
    assert sleep_calls == []
    assert _credits(client, buyer["headers"]) == buyer_before


def test_gemini_429_failover_to_configurable_fallback_provider_succeeds(client):
    owner = _register(client, "qfb_owner")
    buyer = _register(client, "qfb_buyer")
    ds_id, table_name = _upload_public_dataset(client, owner["headers"], name="Fallback Provider Sales")

    buyer_before = _credits(client, buyer["headers"])
    owner_before = _credits(client, owner["headers"])

    gemini_429 = genai_errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "message": "Quota exceeded for metric GenerateRequestsPerDay",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )

    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": f"```sql\nSELECT category, SUM(revenue) AS cat_rev FROM {table_name} GROUP BY category ORDER BY cat_rev DESC\n```"
                }
            }
        ]
    }
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value.post.return_value = mock_http_response

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "test-gemini-key-123456"
    ), patch.object(settings, "AI_FALLBACK_PROVIDER", "openai"), patch.object(
        settings, "AI_FALLBACK_API_KEY", "sk-test-fallback-key-1234567890"
    ), patch.object(settings, "AI_FALLBACK_MODEL", "gpt-4o-mini"), patch.object(
        settings, "AI_MAX_RETRIES", 1
    ), patch("app.services.nl_query._call_gemini_once", side_effect=gemini_429), patch(
        "app.services.nl_query.httpx.Client", return_value=mock_client_instance
    ):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Revenue by category", "dataset_id": ds_id},
        )

    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data["results"]) == 2
    assert data["results"][0] == {"category": "Tech", "cat_rev": 1200}
    assert data["results"][1] == {"category": "Office", "cat_rev": 750}
    assert data["credits_charged"] == 1
    assert _credits(client, buyer["headers"]) == buyer_before - 1
    assert _credits(client, owner["headers"]) == owner_before + 1


def test_gemini_and_fallback_both_429_returns_safe_message_and_zero_credits(client):
    owner = _register(client, "qboth_owner")
    buyer = _register(client, "qboth_buyer")
    ds_id, _ = _upload_public_dataset(client, owner["headers"], name="Dual 429 Sales")

    buyer_before = _credits(client, buyer["headers"])
    owner_before = _credits(client, owner["headers"])
    tx_before = _tx_count([buyer["user_id"], owner["user_id"]])

    gemini_429 = genai_errors.APIError(
        429,
        {"error": {"code": 429, "message": "Quota exceeded daily limit: 0", "status": "RESOURCE_EXHAUSTED"}},
    )

    mock_http_response = MagicMock()
    mock_http_response.status_code = 429
    mock_http_response.text = '{"error":{"message":"You exceeded your current quota, check billing","type":"insufficient_quota"}}'
    mock_http_response.headers = {}
    mock_http_response.request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value.post.return_value = mock_http_response

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "test-gemini-key-123456"
    ), patch.object(settings, "AI_FALLBACK_PROVIDER", "openai"), patch.object(
        settings, "AI_FALLBACK_API_KEY", "sk-test-fallback-key-1234567890"
    ), patch.object(settings, "AI_MAX_RETRIES", 1), patch(
        "app.services.nl_query._call_gemini_once", side_effect=gemini_429
    ), patch("app.services.nl_query.httpx.Client", return_value=mock_client_instance):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Revenue by category", "dataset_id": ds_id},
        )

    assert res.status_code == 503
    assert res.json()["detail"] == AI_QUOTA_USER_MESSAGE
    assert "insufficient_quota" not in res.json()["detail"]
    assert _credits(client, buyer["headers"]) == buyer_before
    assert _credits(client, owner["headers"]) == owner_before
    assert _tx_count([buyer["user_id"], owner["user_id"]]) == tx_before


def test_secret_redaction_helper_strips_all_provider_keys():
    raw = (
        "Failed request with key=AIzaSy1234567890abcdefghijklmnop "
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.sig "
        "and sk-proj1234567890abcdef123456 and gsk_9876543210abcdef123456"
    )
    redacted = _redact_secrets(raw)
    assert "AIzaSy1234567890" not in redacted
    assert "eyJhbGciOiJIUzI1NiJ9" not in redacted
    assert "sk-proj1234567890" not in redacted
    assert "gsk_9876543210" not in redacted
    assert "[REDACTED" in redacted


def test_non_429_gemini_error_is_sanitized_and_does_not_deduct_credits(client):
    owner = _register(client, "q500_owner")
    buyer = _register(client, "q500_buyer")
    ds_id, _ = _upload_public_dataset(client, owner["headers"], name="Sanitized 500 Sales")
    buyer_before = _credits(client, buyer["headers"])

    raw_500 = genai_errors.APIError(
        500,
        {"error": {"code": 500, "message": "Internal Google backend trace: internal_shard_42", "status": "INTERNAL"}},
    )

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "test-gemini-key-123456"
    ), patch.object(settings, "AI_FALLBACK_PROVIDER", None), patch.object(
        settings, "AI_MAX_RETRIES", 0
    ), patch("app.services.nl_query._call_gemini_once", side_effect=raw_500):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Average revenue", "dataset_id": ds_id},
        )

    assert res.status_code == 503
    assert res.json()["detail"] == AI_UNAVAILABLE_USER_MESSAGE
    assert "internal_shard_42" not in res.json()["detail"]
    assert _credits(client, buyer["headers"]) == buyer_before


def test_gemini_429_automatic_groq_fallback_e2e_executes_duckdb_and_charges_only_on_success(client):
    """
    End-to-end test:
    1. Primary Gemini returns HTTP 429 (daily quota exhausted).
    2. Backend automatically falls back to Groq (https://api.groq.com/openai/v1/chat/completions)
       using production model llama-3.3-70b-versatile via GROQ_API_KEY.
    3. Validated SQL executes against DuckDB and returns real query results (never fabricated).
    4. Buyer is charged 1 credit and owner receives 1 credit ONLY after execution succeeds.
    5. If Groq returns invalid/unsafe SQL, query fails with 422 and 0 credits are deducted.
    """
    owner = _register(client, "qgroq_owner")
    buyer = _register(client, "qgroq_buyer")
    ds_id, table_name = _upload_public_dataset(client, owner["headers"], name="Groq Fallback Sales")

    buyer_before = _credits(client, buyer["headers"])
    owner_before = _credits(client, owner["headers"])
    tx_before = _tx_count([buyer["user_id"], owner["user_id"]])

    gemini_429 = genai_errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "message": "Quota exceeded for metric GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 20",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )

    captured_calls = []

    def _mock_groq_post(url, headers=None, json=None):
        captured_calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            f"SELECT item, revenue FROM {table_name} "
                            f"WHERE category ILIKE 'Office' ORDER BY revenue DESC"
                        )
                    }
                }
            ]
        }
        return resp

    mock_http_client = MagicMock()
    mock_http_client.__enter__.return_value.post.side_effect = _mock_groq_post

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "AIzaSyPrimaryGeminiKey1234567890"
    ), patch.object(settings, "AI_FALLBACK_PROVIDER", "groq"), patch.object(
        settings, "GROQ_API_KEY", "gsk_test_groq_fallback_key_1234567890"
    ), patch.object(settings, "AI_FALLBACK_API_KEY", None), patch.object(
        settings, "AI_FALLBACK_MODEL", None
    ), patch.object(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"), patch.object(
        settings, "AI_FALLBACK_BASE_URL", None
    ), patch("app.services.nl_query._call_gemini_once", side_effect=gemini_429), patch(
        "app.services.nl_query.httpx.Client", return_value=mock_http_client
    ):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Show Office items sorted by revenue descending", "dataset_id": ds_id},
        )

    assert res.status_code == 200, res.text
    data = res.json()

    # Verify Groq endpoint, model, and Authorization header were used
    assert len(captured_calls) == 1
    assert captured_calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured_calls[0]["json"]["model"] == "llama-3.3-70b-versatile"
    assert captured_calls[0]["headers"]["Authorization"] == "Bearer gsk_test_groq_fallback_key_1234567890"

    # Verify authentic DuckDB execution results (never fabricated)
    assert data["results"] == [
        {"item": "Desk", "revenue": 450},
        {"item": "Chair", "revenue": 300},
    ]
    assert data["credits_charged"] == 1
    assert _credits(client, buyer["headers"]) == buyer_before - 1
    assert _credits(client, owner["headers"]) == owner_before + 1
    assert _tx_count([buyer["user_id"], owner["user_id"]]) == tx_before + 2

    # Verify if Groq generates invalid SQL, query fails cleanly with 422 and 0 credits charged
    buyer_mid = _credits(client, buyer["headers"])
    owner_mid = _credits(client, owner["headers"])

    def _mock_groq_bad_sql(url, headers=None, json=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": f"SELECT nonexistent_col FROM {table_name}"}}]
        }
        return resp

    mock_http_client.__enter__.return_value.post.side_effect = _mock_groq_bad_sql

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "AIzaSyPrimaryGeminiKey1234567890"
    ), patch.object(settings, "AI_FALLBACK_PROVIDER", "groq"), patch.object(
        settings, "GROQ_API_KEY", "gsk_test_groq_fallback_key_1234567890"
    ), patch.object(settings, "AI_FALLBACK_API_KEY", None), patch.object(
        settings, "GROQ_MODEL", "llama-3.3-70b-versatile"
    ), patch("app.services.nl_query._call_gemini_once", side_effect=gemini_429), patch(
        "app.services.nl_query.httpx.Client", return_value=mock_http_client
    ):
        bad_res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Show nonexistent column", "dataset_id": ds_id},
        )

    assert bad_res.status_code == 422
    assert _credits(client, buyer["headers"]) == buyer_mid
    assert _credits(client, owner["headers"]) == owner_mid


def test_gemini_primary_successful_execution_and_credit_handling(client):
    """Verify Gemini remains primary provider, executes validated DuckDB SQL, and applies exact credit rules."""
    owner = _register(client, "qgem_owner")
    buyer = _register(client, "qgem_buyer")
    ds_id, table_name = _upload_public_dataset(client, owner["headers"], name="Gemini Primary Sales")

    owner_before = _credits(client, owner["headers"])
    buyer_before = _credits(client, buyer["headers"])

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "AIzaSyPrimaryGeminiKey1234567890"
    ), patch(
        "app.services.nl_query._call_gemini_once",
        return_value=f"SELECT COUNT(*) AS cnt, SUM(revenue) AS total_rev FROM {table_name}",
    ) as gemini_mock:
        # 1. Owner self-query -> 0 credits charged, 0 owner reward
        own_res = client.post(
            "/query",
            headers=owner["headers"],
            json={"query": "Count and sum revenue", "dataset_id": ds_id},
        )
        assert own_res.status_code == 200, own_res.text
        assert own_res.json()["credits_charged"] == 0
        assert own_res.json()["results"][0] == {"cnt": 3, "total_rev": 1950}
        assert _credits(client, owner["headers"]) == owner_before

        # 2. Non-owner paid query -> buyer -1 cr, owner +1 cr
        buyer_res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Count and sum revenue", "dataset_id": ds_id},
        )
        assert buyer_res.status_code == 200, buyer_res.text
        assert buyer_res.json()["credits_charged"] == 1
        assert buyer_res.json()["results"][0] == {"cnt": 3, "total_rev": 1950}
        assert _credits(client, buyer["headers"]) == buyer_before - 1
        assert _credits(client, owner["headers"]) == owner_before + 1
        assert gemini_mock.call_count == 2


def test_groq_authentication_failure_fails_fast_redacts_secret_and_charges_zero_credits(client, caplog):
    """Verify Groq HTTP 401/403 fails immediately (no retries), hides technical details, redacts key, and charges 0 credits."""
    owner = _register(client, "qgauth_owner")
    buyer = _register(client, "qgauth_buyer")
    ds_id, _ = _upload_public_dataset(client, owner["headers"], name="Groq Auth Fail Sales")

    buyer_before = _credits(client, buyer["headers"])
    owner_before = _credits(client, owner["headers"])
    tx_before = _tx_count([buyer["user_id"], owner["user_id"]])

    fake_groq_key = "gsk_super_secret_invalid_groq_key_987654321"
    gemini_429 = genai_errors.APIError(
        429,
        {"error": {"code": 429, "message": "Quota exceeded daily limit: 0", "status": "RESOURCE_EXHAUSTED"}},
    )

    groq_calls = 0

    def _mock_groq_401(url, headers=None, json=None):
        nonlocal groq_calls
        groq_calls += 1
        resp = MagicMock()
        resp.status_code = 401
        resp.text = f'{{"error":{{"message":"Invalid API key: {fake_groq_key}","type":"invalid_request_error"}}}}'
        resp.headers = {}
        resp.request = httpx.Request("POST", url)
        return resp

    mock_http_client = MagicMock()
    mock_http_client.__enter__.return_value.post.side_effect = _mock_groq_401

    with caplog.at_level(logging.ERROR, logger="app.services.nl_query"), patch.object(
        settings, "AI_PROVIDER", "gemini"
    ), patch.object(settings, "GEMINI_API_KEY", "AIzaSyPrimaryGeminiKey1234567890"), patch.object(
        settings, "AI_FALLBACK_PROVIDER", "groq"
    ), patch.object(settings, "GROQ_API_KEY", fake_groq_key), patch.object(
        settings, "AI_FALLBACK_API_KEY", None
    ), patch.object(settings, "AI_MAX_RETRIES", 2), patch(
        "app.services.nl_query._call_gemini_once", side_effect=gemini_429
    ), patch("app.services.nl_query.httpx.Client", return_value=mock_http_client):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Revenue breakdown", "dataset_id": ds_id},
        )

    assert res.status_code == 503
    assert res.json()["detail"] == AI_QUOTA_USER_MESSAGE
    assert fake_groq_key not in res.json()["detail"]
    assert "Invalid API key" not in res.json()["detail"]
    # Auth 401 must fail fast with 1 attempt (no pointless retries or backup model loops)
    assert groq_calls == 1
    assert _credits(client, buyer["headers"]) == buyer_before
    assert _credits(client, owner["headers"]) == owner_before
    assert _tx_count([buyer["user_id"], owner["user_id"]]) == tx_before

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert fake_groq_key not in log_text
    assert "[REDACTED" in log_text


def test_groq_model_not_found_404_auto_recovers_to_backup_model_and_strips_think_tags(client):
    """Verify HTTP 404 model_not_found on primary Groq model seamlessly tries configured GROQ_BACKUP_MODELS."""
    owner = _register(client, "qg404_owner")
    buyer = _register(client, "qg404_buyer")
    ds_id, table_name = _upload_public_dataset(client, owner["headers"], name="Groq Backup Model Sales")

    gemini_429 = genai_errors.APIError(
        429,
        {"error": {"code": 429, "message": "Quota exceeded daily limit: 0", "status": "RESOURCE_EXHAUSTED"}},
    )

    attempted_models = []

    def _mock_groq_post(url, headers=None, json=None):
        model = (json or {}).get("model")
        attempted_models.append(model)
        resp = MagicMock()
        resp.request = httpx.Request("POST", url)
        resp.headers = {}
        if model == "llama-3.3-70b-versatile":
            resp.status_code = 404
            resp.text = '{"error":{"message":"The model `llama-3.3-70b-versatile` does not exist","code":"model_not_found"}}'
            return resp
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": f"<think>Calculate max revenue</think>\n```sql\nSELECT item, revenue FROM {table_name} ORDER BY revenue DESC LIMIT 1\n```"
                    }
                }
            ]
        }
        return resp

    mock_http_client = MagicMock()
    mock_http_client.__enter__.return_value.post.side_effect = _mock_groq_post

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "AIzaSyPrimaryGeminiKey1234567890"
    ), patch.object(settings, "AI_FALLBACK_PROVIDER", "groq"), patch.object(
        settings, "GROQ_API_KEY", "gsk_test_groq_key_1234567890"
    ), patch.object(settings, "AI_FALLBACK_API_KEY", None), patch.object(
        settings, "GROQ_MODEL", "llama-3.3-70b-versatile"
    ), patch.object(settings, "GROQ_BACKUP_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b"), patch(
        "app.services.nl_query._call_gemini_once", side_effect=gemini_429
    ), patch("app.services.nl_query.httpx.Client", return_value=mock_http_client):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Highest revenue item", "dataset_id": ds_id},
        )

    assert res.status_code == 200, res.text
    assert attempted_models == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
    assert res.json()["results"] == [{"item": "Laptop", "revenue": 1200}]


def test_groq_is_default_primary_provider_and_executes_without_calling_gemini(client):
    """
    Verify Groq (llama-3.3-70b-versatile) is the default primary AI provider,
    executes validated SQL against DuckDB without invoking Gemini, and applies exact credit rules.
    """
    from app.config import Settings

    assert Settings.model_fields["AI_PROVIDER"].default == "groq"
    assert Settings.model_fields["GROQ_MODEL"].default == "llama-3.3-70b-versatile"
    assert Settings.model_fields["AI_FALLBACK_PROVIDER"].default == "gemini"

    owner = _register(client, "gprim_owner")
    buyer = _register(client, "gprim_buyer")
    ds_id, table_name = _upload_public_dataset(client, owner["headers"], name="Groq Primary Sales")

    owner_before = _credits(client, owner["headers"])
    buyer_before = _credits(client, buyer["headers"])

    captured = []

    def _mock_groq_post(url, headers=None, json=None):
        captured.append({"url": url, "headers": headers or {}, "json": json or {}})
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": f"SELECT item, revenue FROM {table_name} ORDER BY revenue DESC LIMIT 1"
                    }
                }
            ]
        }
        return resp

    mock_http_client = MagicMock()
    mock_http_client.__enter__.return_value.post.side_effect = _mock_groq_post

    with patch.object(settings, "AI_PROVIDER", "groq"), patch.object(
        settings, "GROQ_API_KEY", "gsk_primary_groq_test_key_123456"
    ), patch.object(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"), patch.object(
        settings, "AI_FALLBACK_PROVIDER", "gemini"
    ), patch.object(settings, "GEMINI_API_KEY", "AIzaSyOptionalGeminiFallback123456"), patch(
        "app.services.nl_query.httpx.Client", return_value=mock_http_client
    ), patch(
        "app.services.nl_query._call_gemini_once",
        side_effect=AssertionError("Gemini must NOT be called when primary Groq succeeds"),
    ):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Top revenue item", "dataset_id": ds_id},
        )

    assert res.status_code == 200, res.text
    assert len(captured) == 1
    assert captured[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured[0]["json"]["model"] == "llama-3.3-70b-versatile"
    assert captured[0]["headers"]["Authorization"] == "Bearer gsk_primary_groq_test_key_123456"
    assert res.json()["results"] == [{"item": "Laptop", "revenue": 1200}]
    assert res.json()["credits_charged"] == 1
    assert _credits(client, buyer["headers"]) == buyer_before - 1
    assert _credits(client, owner["headers"]) == owner_before + 1


def test_groq_primary_failure_falls_back_to_optional_gemini_when_configured(client):
    """When primary Groq fails with HTTP 429 and optional GEMINI_API_KEY is set, Gemini fallback executes SQL."""
    owner = _register(client, "g2gem_owner")
    buyer = _register(client, "g2gem_buyer")
    ds_id, table_name = _upload_public_dataset(client, owner["headers"], name="Groq To Gemini Sales")

    owner_before = _credits(client, owner["headers"])
    buyer_before = _credits(client, buyer["headers"])

    def _mock_groq_429(url, headers=None, json=None):
        resp = MagicMock()
        resp.status_code = 429
        resp.text = '{"error":{"message":"Quota exceeded daily limit: 0"}}'
        resp.headers = {}
        resp.request = httpx.Request("POST", url)
        return resp

    mock_http_client = MagicMock()
    mock_http_client.__enter__.return_value.post.side_effect = _mock_groq_429

    with patch.object(settings, "AI_PROVIDER", "groq"), patch.object(
        settings, "GROQ_API_KEY", "gsk_primary_groq_test_key_123456"
    ), patch.object(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"), patch.object(
        settings, "AI_FALLBACK_PROVIDER", "gemini"
    ), patch.object(settings, "GEMINI_API_KEY", "AIzaSyOptionalGeminiFallback123456"), patch.object(
        settings, "AI_FALLBACK_API_KEY", None
    ), patch("app.services.nl_query.httpx.Client", return_value=mock_http_client), patch(
        "app.services.nl_query._call_gemini_once",
        return_value=f"SELECT SUM(revenue) AS total_rev FROM {table_name}",
    ) as gemini_mock:
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Total revenue across all items", "dataset_id": ds_id},
        )

    assert res.status_code == 200, res.text
    assert gemini_mock.call_count == 1
    assert res.json()["results"] == [{"total_rev": 1950}]
    assert res.json()["credits_charged"] == 1
    assert _credits(client, buyer["headers"]) == buyer_before - 1
    assert _credits(client, owner["headers"]) == owner_before + 1


def test_groq_primary_failure_without_gemini_key_returns_safe_error_redacts_key_and_zero_credits(client, caplog):
    """When primary Groq fails and optional Gemini is NOT configured, return safe 503 with 0 credits charged."""
    owner = _register(client, "gnogem_owner")
    buyer = _register(client, "gnogem_buyer")
    ds_id, _ = _upload_public_dataset(client, owner["headers"], name="Groq No Fallback Sales")

    owner_before = _credits(client, owner["headers"])
    buyer_before = _credits(client, buyer["headers"])
    tx_before = _tx_count([buyer["user_id"], owner["user_id"]])
    fake_groq_key = "gsk_primary_secret_key_must_never_leak_999"

    def _mock_groq_429(url, headers=None, json=None):
        resp = MagicMock()
        resp.status_code = 429
        resp.text = f'{{"error":{{"message":"Rate limit exceeded daily limit: 0 for {fake_groq_key}"}}}}'
        resp.headers = {}
        resp.request = httpx.Request("POST", url)
        return resp

    mock_http_client = MagicMock()
    mock_http_client.__enter__.return_value.post.side_effect = _mock_groq_429

    with caplog.at_level(logging.WARNING, logger="app.services.nl_query"), patch.object(
        settings, "AI_PROVIDER", "groq"
    ), patch.object(settings, "GROQ_API_KEY", fake_groq_key), patch.object(
        settings, "AI_FALLBACK_PROVIDER", "gemini"
    ), patch.object(settings, "GEMINI_API_KEY", None), patch.object(
        settings, "AI_FALLBACK_API_KEY", None
    ), patch("app.services.nl_query.httpx.Client", return_value=mock_http_client):
        res = client.post(
            "/query",
            headers=buyer["headers"],
            json={"query": "Average revenue", "dataset_id": ds_id},
        )

    assert res.status_code == 503
    assert res.json()["detail"] == AI_QUOTA_USER_MESSAGE
    assert fake_groq_key not in res.json()["detail"]
    assert _credits(client, buyer["headers"]) == buyer_before
    assert _credits(client, owner["headers"]) == owner_before
    assert _tx_count([buyer["user_id"], owner["user_id"]]) == tx_before

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert fake_groq_key not in log_text
    assert "[REDACTED" in log_text




