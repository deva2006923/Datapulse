import os
import sys
import time
import uuid
import httpx

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def log_result(step_name: str, passed: bool, detail: str = ""):
    status_str = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    detail_str = f" - {detail}" if detail else ""
    print(f"[{status_str}] {BOLD}{step_name}{RESET}{detail_str}")

def run_smoke_test():
    print(f"Starting DataPulse Smoke Test against: {BASE_URL}\n")
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)
    all_passed = True

    # Step 0: Check Health
    try:
        res = client.get("/health")
        if res.status_code == 200:
            data = res.json()
            log_result("1. GET /health", True, f"status: {data.get('status')}, cors_regex: {data.get('cors_regex')}, embeddings: {data.get('embeddings')}")
        else:
            log_result("1. GET /health", False, f"Status code {res.status_code}")
            all_passed = False
    except Exception as e:
        log_result("1. GET /health", False, f"Connection error: {e}")
        all_passed = False
        return False

    # Step 1: Register
    unique_id = uuid.uuid4().hex[:8]
    test_email = f"smoketest_{unique_id}@datapulse.io"
    test_password = "SecurePassword123!"
    registered_token = None
    
    try:
        res = client.post("/auth/register", json={
            "email": test_email,
            "password": test_password,
            "full_name": f"Smoke Test User {unique_id}"
        })
        if res.status_code == 201:
            data = res.json()
            registered_token = data.get("access_token")
            log_result("2. Register (/auth/register)", True, f"Created user {test_email}")
        else:
            log_result("2. Register (/auth/register)", False, f"Status {res.status_code}: {res.text}")
            all_passed = False
    except Exception as e:
        log_result("2. Register (/auth/register)", False, f"Exception: {e}")
        all_passed = False

    # Step 2: Login
    auth_token = None
    try:
        res = client.post("/auth/login", json={
            "email": test_email,
            "password": test_password
        })
        if res.status_code == 200:
            data = res.json()
            auth_token = data.get("access_token")
            log_result("3. Login (/auth/login)", True, f"Obtained Bearer token")
        else:
            log_result("3. Login (/auth/login)", False, f"Status {res.status_code}: {res.text}")
            all_passed = False
    except Exception as e:
        log_result("3. Login (/auth/login)", False, f"Exception: {e}")
        all_passed = False

    token_to_use = auth_token or registered_token
    auth_headers = {"Authorization": f"Bearer {token_to_use}"} if token_to_use else {}

    # Step 3: Upload Small Generated CSV
    dataset_id = None
    csv_data = "metric_id,category,score,observed_value\n101,performance,98.5,450\n102,reliability,99.1,510\n103,latency,92.0,120\n104,throughput,96.4,850\n"
    try:
        files = {"file": ("sample_metrics.csv", csv_data, "text/csv")}
        data = {"domain": "technology", "name": f"Metrics Batch {unique_id}"}
        res = client.post("/datasets/upload", headers=auth_headers, files=files, data=data)
        if res.status_code in (200, 201):
            res_data = res.json()
            dataset_id = res_data.get("id")
            log_result("4. Upload CSV (/datasets/upload)", True, f"Dataset ID: {dataset_id}")
        else:
            log_result("4. Upload CSV (/datasets/upload)", False, f"Status {res.status_code}: {res.text}")
            all_passed = False
    except Exception as e:
        log_result("4. Upload CSV (/datasets/upload)", False, f"Exception: {e}")
        all_passed = False

    # Step 4: Poll /datasets/{id}/evaluation until completed
    evaluation_done = False
    try:
        if dataset_id:
            max_attempts = 10
            for attempt in range(max_attempts):
                res = client.get(f"/datasets/{dataset_id}/evaluation", headers=auth_headers)
                if res.status_code == 200:
                    eval_data = res.json()
                    status_val = eval_data.get("status")
                    if status_val == "completed":
                        evaluation_done = True
                        log_result(
                            "5. Poll Evaluation (/datasets/{id}/evaluation)", 
                            True, 
                            f"Status: {status_val}, Overall Score: {eval_data.get('overall_score')}, Credits Awarded: {eval_data.get('credits_awarded')}"
                        )
                        break
                    time.sleep(0.5)
                else:
                    time.sleep(0.5)
            if not evaluation_done:
                log_result("5. Poll Evaluation (/datasets/{id}/evaluation)", False, "Evaluation did not complete in time")
                all_passed = False
        else:
            log_result("5. Poll Evaluation (/datasets/{id}/evaluation)", False, "Skipped due to upload failure")
            all_passed = False
    except Exception as e:
        log_result("5. Poll Evaluation (/datasets/{id}/evaluation)", False, f"Exception: {e}")
        all_passed = False

    # Step 5: Search
    try:
        res = client.post("/datasets/search", json={"query": "technology metrics throughput", "limit": 5})
        if res.status_code == 200:
            s_data = res.json()
            results = s_data.get("results", [])
            log_result("6. Search (/datasets/search)", True, f"Found {len(results)} matches (method: {s_data.get('method')})")
        else:
            log_result("6. Search (/datasets/search)", False, f"Status {res.status_code}: {res.text}")
            all_passed = False
    except Exception as e:
        log_result("6. Search (/datasets/search)", False, f"Exception: {e}")
        all_passed = False

    # Step 6: Query
    try:
        res = client.post("/query", json={"query": "What is the average performance metric?"}, headers=auth_headers)
        if res.status_code == 200:
            q_data = res.json()
            log_result("7. Query (/query)", True, f"Confidence: {q_data.get('relevance_score')}, Records: {q_data.get('records_analyzed')}")
        else:
            log_result("7. Query (/query)", False, f"Status {res.status_code}: {res.text}")
            all_passed = False
    except Exception as e:
        log_result("7. Query (/query)", False, f"Exception: {e}")
        all_passed = False

    # Step 7: Redeem Validation Error
    try:
        # Intentionally sending invalid amount <= 0 to trigger validation error (HTTP 422)
        res = client.post("/credits/redeem", json={"amount": -50, "payout_method": "upi", "destination": "test@upi"}, headers=auth_headers)
        if res.status_code == 422:
            log_result("8. Redeem Validation Error (/credits/redeem)", True, f"Correctly returned HTTP 422 Unprocessable Entity for invalid payload")
        else:
            # Also test balance excess
            res2 = client.post("/credits/redeem", json={"amount": 999999, "payout_method": "upi", "destination": "test@upi"}, headers=auth_headers)
            if res2.status_code in (400, 422):
                log_result("8. Redeem Validation Error (/credits/redeem)", True, f"Correctly returned HTTP {res2.status_code} for excessive balance redemption")
            else:
                log_result("8. Redeem Validation Error (/credits/redeem)", False, f"Expected 422/400 validation error, got {res.status_code}")
                all_passed = False
    except Exception as e:
        log_result("8. Redeem Validation Error (/credits/redeem)", False, f"Exception: {e}")
        all_passed = False

    # Step 8: /me/stats
    try:
        res = client.get("/me/stats", headers=auth_headers)
        if res.status_code == 200:
            stats = res.json()
            log_result(
                "9. User Stats (/me/stats)", 
                True, 
                f"Balance: {stats.get('credits_balance')} credits, Uploads: {stats.get('datasets_uploaded')}, Avg Score: {stats.get('average_quality_score')}"
            )
        else:
            log_result("9. User Stats (/me/stats)", False, f"Status {res.status_code}: {res.text}")
            all_passed = False
    except Exception as e:
        log_result("9. User Stats (/me/stats)", False, f"Exception: {e}")
        all_passed = False

    print("\n---------------------------------------------------")
    if all_passed:
        print(f"{GREEN}{BOLD}ALL SMOKE TESTS PASSED! DataPulse backend is ready.{RESET}")
        return True
    else:
        print(f"{RED}{BOLD}SOME SMOKE TESTS FAILED! Check logs above.{RESET}")
        return False

if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
