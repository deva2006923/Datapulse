import uuid
import pytest
from app.database import get_db_connection
from app.services.storage import get_dataset_table_name, delete_dataset_storage
from app.services.nl_query import set_ai_generator


def _register(client, prefix: str):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"User {prefix}"},
    )
    assert res.status_code == 201
    data = res.json()
    return {
        "id": data["user"]["id"],
        "email": email,
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _upload_csv(client, headers, name: str, filename: str, domain: str, csv_text: str):
    res = client.post(
        "/datasets/upload",
        headers=headers,
        files={"file": (filename, csv_text.encode("utf-8"), "text/csv")},
        data={"domain": domain, "name": name},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_three_distinct_datasets_dynamic_selection_and_switching(client):
    """
    Uploads 3 datasets with distinct names, schemas, and column types, verifies all 3
    appear in GET /datasets with real storage availability, and confirms switching
    dataset_id dynamically changes the DuckDB SQL execution target and results.
    """
    owner = _register(client, "dyn_owner")
    analyst = _register(client, "dyn_analyst")

    csv_hospital = (
        "patient_code,age,bill_amount,ward\n"
        "P101,45,1250.50,Cardiology\n"
        "P102,62,3400.00,Neurology\n"
        "P103,29,480.25,Orthopedics\n"
    )
    csv_fleet = (
        "vehicle_id,mileage_km,fuel_liters,active_route\n"
        "TRK-01,14200,88.5,North\n"
        "TRK-02,28950,154.2,South\n"
    )
    csv_books = (
        "isbn,title,copies_in_stock,unit_price\n"
        "978-01,Data Systems,14,49.99\n"
        "978-02,SQL Mastery,7,39.50\n"
        "978-03,DuckDB Guide,22,29.00\n"
        "978-04,Python Analytics,5,54.00\n"
    )

    ds1 = _upload_csv(client, owner["headers"], "Hospital Admissions", "hospital.csv", "healthcare", csv_hospital)
    ds2 = _upload_csv(client, owner["headers"], "Fleet Telemetry", "fleet.csv", "logistics", csv_fleet)
    ds3 = _upload_csv(client, owner["headers"], "Bookstore Inventory", "books.csv", "retail", csv_books)

    # 1. Verify all 3 datasets appear dynamically in GET /datasets with real availability & schemas
    catalog_res = client.get("/datasets")
    assert catalog_res.status_code == 200
    catalog_map = {d["id"]: d for d in catalog_res.json()["datasets"]}

    for ds, expected_rows, expected_cols in [
        (ds1, 3, 4),
        (ds2, 2, 4),
        (ds3, 4, 4),
    ]:
        assert ds["id"] in catalog_map
        entry = catalog_map[ds["id"]]
        assert entry["name"] == ds["name"]
        assert entry["rows_count"] == expected_rows
        assert entry["columns_count"] == expected_cols
        assert entry["storage_available"] is True
        assert entry["availability"] == "Available"

    # 2. Switch across all 3 datasets and verify dynamic schema-aware SQL generation & target table
    seen_targets = []

    def dynamic_generator(question: str, table_name: str, cols):
        col_names = [c[0] for c in cols]
        seen_targets.append((table_name, col_names))
        if "patient_code" in col_names:
            return f"SELECT patient_code, ward, bill_amount FROM {table_name} ORDER BY bill_amount DESC"
        if "vehicle_id" in col_names:
            return f"SELECT vehicle_id, mileage_km FROM {table_name} ORDER BY mileage_km DESC"
        if "isbn" in col_names:
            return f"SELECT isbn, title, copies_in_stock FROM {table_name} ORDER BY copies_in_stock DESC"
        return f"SELECT * FROM {table_name} LIMIT 5"

    set_ai_generator(dynamic_generator)
    try:
        # Owner queries dataset 1 -> 0 credits charged
        owner_before = client.get("/auth/me", headers=owner["headers"]).json()["credits"]
        r1 = client.post(
            "/query",
            headers=owner["headers"],
            json={"query": "Highest hospital bills", "dataset_id": ds1["id"]},
        )
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert b1["dataset_id"] == ds1["id"]
        assert get_dataset_table_name(ds1["id"]) in b1["sql_query"]
        assert b1["results"][0]["patient_code"] == "P102"
        assert b1["credits_charged"] == 0
        assert client.get("/auth/me", headers=owner["headers"]).json()["credits"] == owner_before

        # Analyst queries dataset 2 -> 1 credit deducted from analyst, +1 rewarded to owner
        analyst_before = client.get("/auth/me", headers=analyst["headers"]).json()["credits"]
        owner_before = client.get("/auth/me", headers=owner["headers"]).json()["credits"]
        r2 = client.post(
            "/query",
            headers=analyst["headers"],
            json={"query": "Highest mileage trucks", "dataset_id": ds2["id"]},
        )
        assert r2.status_code == 200, r2.text
        b2 = r2.json()
        assert b2["dataset_id"] == ds2["id"]
        assert get_dataset_table_name(ds2["id"]) in b2["sql_query"]
        assert b2["results"][0]["vehicle_id"] == "TRK-02"
        assert b2["credits_charged"] == 1
        assert client.get("/auth/me", headers=analyst["headers"]).json()["credits"] == analyst_before - 1
        assert client.get("/auth/me", headers=owner["headers"]).json()["credits"] == owner_before + 1

        # Analyst switches to dataset 3 -> targets ds3 DuckDB table & Bookstore columns
        r3 = client.post(
            "/query",
            headers=analyst["headers"],
            json={"query": "Most stocked books", "dataset_id": ds3["id"]},
        )
        assert r3.status_code == 200, r3.text
        b3 = r3.json()
        assert b3["dataset_id"] == ds3["id"]
        assert get_dataset_table_name(ds3["id"]) in b3["sql_query"]
        assert b3["results"][0]["isbn"] == "978-03"
        assert b3["credits_charged"] == 1

        # Confirm 3 distinct DuckDB tables were targeted
        targeted_tables = [t for t, _ in seen_targets]
        assert targeted_tables == [
            get_dataset_table_name(ds1["id"]),
            get_dataset_table_name(ds2["id"]),
            get_dataset_table_name(ds3["id"]),
        ]

        # Confirm query history recorded exact dataset IDs for the authenticated analyst
        hist = client.get("/query/history", headers=analyst["headers"]).json()
        hist_ds_ids = [item["dataset_id"] for item in hist["items"]]
        assert ds2["id"] in hist_ds_ids
        assert ds3["id"] in hist_ds_ids
        assert ds1["id"] not in hist_ds_ids
    finally:
        set_ai_generator(None)


def test_missing_dataset_and_failed_queries_never_deduct_credits(client):
    """
    Verifies missing/hardcoded demo dataset IDs (such as 'ds-retail-b'), missing DuckDB
    tables, and rejected SQL statements return friendly errors and never deduct credits.
    """
    owner = _register(client, "fail_owner")
    querier = _register(client, "fail_querier")

    ds = _upload_csv(
        client,
        owner["headers"],
        "Weather Observations",
        "weather.csv",
        "general",
        "city,temp_c,humidity\nSeattle,14.5,78\nAustin,31.2,45\n",
    )

    balance_before = client.get("/auth/me", headers=querier["headers"]).json()["credits"]

    # 1. Legacy hardcoded demo dataset ID -> 404 friendly error, 0 credits charged
    missing_res = client.post(
        "/query",
        headers=querier["headers"],
        json={"query": "How many rows?", "dataset_id": "ds-retail-b"},
    )
    assert missing_res.status_code == 404
    assert "not found" in missing_res.json()["detail"].lower()
    assert client.get("/auth/me", headers=querier["headers"]).json()["credits"] == balance_before

    # 2. Rejected destructive SQL -> 422 security error, 0 credits charged
    set_ai_generator(lambda q, t, cols: f"DROP TABLE {t}")
    try:
        sec_res = client.post(
            "/query",
            headers=querier["headers"],
            json={"query": "Delete everything", "dataset_id": ds["id"]},
        )
        assert sec_res.status_code == 422
        assert client.get("/auth/me", headers=querier["headers"]).json()["credits"] == balance_before
    finally:
        set_ai_generator(None)

    # 3. Unknown column error -> 422 validation error, 0 credits charged
    set_ai_generator(lambda q, t, cols: f"SELECT nonexistent_col FROM {t}")
    try:
        col_res = client.post(
            "/query",
            headers=querier["headers"],
            json={"query": "Show nonexistent column", "dataset_id": ds["id"]},
        )
        assert col_res.status_code == 422
        assert client.get("/auth/me", headers=querier["headers"]).json()["credits"] == balance_before
    finally:
        set_ai_generator(None)

    # 4. Dataset metadata exists but DuckDB storage table was deleted -> reported Unavailable & 404 with 0 credits charged
    delete_dataset_storage(ds["id"])
    detail_after_drop = client.get(f"/datasets/{ds['id']}").json()
    assert detail_after_drop["storage_available"] is False
    assert detail_after_drop["availability"] == "Unavailable"

    missing_table_res = client.post(
        "/query",
        headers=querier["headers"],
        json={"query": "Count rows", "dataset_id": ds["id"]},
    )
    assert missing_table_res.status_code == 404
    assert client.get("/auth/me", headers=querier["headers"]).json()["credits"] == balance_before
