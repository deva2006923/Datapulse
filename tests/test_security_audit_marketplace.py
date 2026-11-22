import io
import uuid
from concurrent.futures import ThreadPoolExecutor

from starlette.testclient import TestClient

from app.database import get_db_connection
from app.main import app
from app.services.storage import dataset_table_exists, get_dataset_rows


def _register(client, prefix: str = "mkt"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@datapulse.io"
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"User {prefix}"},
    )
    assert res.status_code == 201
    data = res.json()
    return {
        "id": data["user"]["id"],
        "email": email,
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def test_concurrent_credit_redemption_cannot_double_spend_or_go_negative():
    """6 concurrent 60-credit redemptions against a 100-credit balance: strictly 1 succeeds, balance stays 40."""
    setup_client = TestClient(app)
    user = _register(setup_client, "redeem_race")

    def attempt(_i: int):
        with TestClient(app) as c:
            return c.post(
                "/credits/redeem",
                headers=user["headers"],
                json={"amount": 60, "payout_method": "upi", "destination": "race@upi"},
            ).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(attempt, range(6)))

    assert codes.count(200) == 1
    assert codes.count(400) == 5

    me = setup_client.get("/auth/me", headers=user["headers"]).json()
    assert me["credits"] == 40
    assert me["credits"] >= 0


def test_duplicate_upload_by_same_user_rejected_without_extra_credits(client):
    """Uploading identical CSV content twice by the same user is rejected with 409 and awards 0 extra credits."""
    user = _register(client, "dup_farm")
    csv_body = f"sku,units,revenue\nSKU-{uuid.uuid4().hex[:6]},15,450.5\nSKU-2,22,610.0\n"

    r1 = client.post(
        "/datasets/upload",
        headers=user["headers"],
        data={"domain": "retail", "name": "Original Sales"},
        files={"file": ("sales1.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
    )
    assert r1.status_code == 201
    balance_after_first = client.get("/auth/me", headers=user["headers"]).json()["credits"]

    # Attempt to farm credits by re-uploading identical CSV with a different filename
    r2 = client.post(
        "/datasets/upload",
        headers=user["headers"],
        data={"domain": "retail", "name": "Renamed Duplicate"},
        files={"file": ("sales2.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
    )
    assert r2.status_code == 409
    assert "duplicate" in r2.json()["detail"].lower()

    balance_after_second = client.get("/auth/me", headers=user["headers"]).json()["credits"]
    assert balance_after_second == balance_after_first


def test_csv_formula_injection_sanitized_and_binary_rejected(client):
    """Spreadsheet formula payloads are neutralized while signed numbers remain intact; binary NUL CSV rejected."""
    user = _register(client, "csv_sec")

    # Binary NUL-byte payload rejected cleanly
    bad_bytes = b"col1,col2\nval1,\x00evil\n"
    bad_res = client.post(
        "/datasets/upload",
        headers=user["headers"],
        data={"domain": "general", "name": "Null Bytes"},
        files={"file": ("bad.csv", io.BytesIO(bad_bytes), "text/csv")},
    )
    assert bad_res.status_code == 422

    # Formula injection CSV + legitimate signed negative number
    formula_csv = (
        "label,amount,note\n"
        "=CMD|' /C calc'!A0,-42.5,@SUM(1+1)\n"
        "+1+1+cmd|calc,100,-2+3+cmd\n"
    )
    ok_res = client.post(
        "/datasets/upload",
        headers=user["headers"],
        data={"domain": "finance", "name": "Formula Sanitized"},
        files={"file": ("formulas.csv", io.BytesIO(formula_csv.encode("utf-8")), "text/csv")},
    )
    assert ok_res.status_code == 201
    ds_id = ok_res.json()["id"]

    rows = get_dataset_rows(ds_id)
    assert len(rows) == 2
    assert str(rows[0]["label"]).startswith("'=CMD")
    assert str(rows[0]["note"]).startswith("'@SUM")
    assert float(rows[0]["amount"]) == -42.5  # legitimate negative number preserved
    assert str(rows[1]["label"]).startswith("'+1+1")
    assert str(rows[1]["note"]).startswith("'-2+3")


def test_concurrent_dataset_unlock_charges_and_rewards_strictly_once():
    """6 concurrent unlock requests charge buyer once and pay owner royalty once."""
    setup_client = TestClient(app)
    owner = _register(setup_client, "unl_owner")
    buyer = _register(setup_client, "unl_buyer")

    csv_body = f"metric,val\nM-{uuid.uuid4().hex[:6]},10\nM-2,20\n"
    up = setup_client.post(
        "/datasets/upload",
        headers=owner["headers"],
        data={"domain": "technology", "name": "Concurrent Unlock DS"},
        files={"file": ("unlock.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
    )
    assert up.status_code == 201
    ds_id = up.json()["id"]
    price = up.json()["unlock_price"]

    owner_before = setup_client.get("/auth/me", headers=owner["headers"]).json()["credits"]
    buyer_before = setup_client.get("/auth/me", headers=buyer["headers"]).json()["credits"]

    def attempt(_i: int):
        with TestClient(app) as c:
            res = c.post(f"/datasets/{ds_id}/unlock", headers=buyer["headers"])
            assert res.status_code == 200
            return res.json()["credits_charged"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        charges = list(pool.map(attempt, range(6)))

    assert charges.count(price) == 1
    assert charges.count(0) == 5

    owner_after = setup_client.get("/auth/me", headers=owner["headers"]).json()["credits"]
    buyer_after = setup_client.get("/auth/me", headers=buyer["headers"]).json()["credits"]
    assert buyer_after == buyer_before - price
    assert owner_after == owner_before + price


def test_dataset_improve_and_delete_enforce_ownership(client):
    """Only dataset owner (or verified admin) can improve or delete a dataset; deletion preserves ledger."""
    owner = _register(client, "own_del")
    stranger = _register(client, "stranger")

    csv_body = f"id,score\n1,80\n2,{uuid.uuid4().int % 99}\n"
    up = client.post(
        "/datasets/upload",
        headers=owner["headers"],
        data={"domain": "education", "name": "Owner Only DS"},
        files={"file": ("owner.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
    )
    assert up.status_code == 201
    ds_id = up.json()["id"]

    # Stranger cannot submit improvement (403)
    imp_forbidden = client.post(
        f"/datasets/{ds_id}/improve",
        headers=stranger["headers"],
        json={"new_quality_score": 99.0, "new_relevance_score": 99.0, "changes_summary": "Unauthorized hijack"},
    )
    assert imp_forbidden.status_code == 403

    # Stranger cannot delete dataset (403)
    del_forbidden = client.delete(f"/datasets/{ds_id}", headers=stranger["headers"])
    assert del_forbidden.status_code == 403
    assert dataset_table_exists(ds_id) is True

    # Owner can delete dataset cleanly
    del_ok = client.delete(f"/datasets/{ds_id}", headers=owner["headers"])
    assert del_ok.status_code == 200
    assert del_ok.json()["deleted"] is True
    assert dataset_table_exists(ds_id) is False
    assert client.get(f"/datasets/{ds_id}").status_code == 404

    # Immutable credit transaction history for owner remains intact
    owner_txs = client.get("/credits/transactions", headers=owner["headers"]).json()
    assert any(t["transaction_type"] == "upload_reward" for t in owner_txs)
