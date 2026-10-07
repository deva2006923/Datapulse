import os
import pytest
from app.services.storage import (
    get_dataset_row_count,
    get_dataset_columns,
    dataset_table_exists,
    get_dataset_rows,
    get_dataset_table_name,
    get_duckdb_connection
)
from app.config import settings
from app.database import get_db_connection


import uuid

@pytest.fixture
def auth_header(client):
    """Helper to create a fresh user and return Authorization header."""
    unique_email = f"tester_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post("/auth/register", json={
        "email": unique_email,
        "password": "Password123!",
        "full_name": "Storage Tester"
    })
    assert res.status_code == 201
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_valid_csv_upload_and_persistence(client, auth_header):
    csv_data = (
        "transaction_id,customer_name,amount,is_flagged\n"
        "tx_101,Alice,150.50,false\n"
        "tx_102,Bob,45.00,false\n"
        "tx_103,Charlie,1200.00,true\n"
        "tx_104,Diana,89.90,false\n"
        "tx_105,Evan,540.25,true\n"
    )
    files = {"file": ("transactions.csv", csv_data, "text/csv")}
    upload_res = client.post(
        "/datasets/upload",
        headers=auth_header,
        files=files,
        data={"domain": "finance", "name": "Financial Transactions"}
    )
    assert upload_res.status_code == 201
    data = upload_res.json()
    dataset_id = data["id"]

    # 1. Check API contract response schema
    assert dataset_id.startswith("ds_")
    assert data["name"] == "Financial Transactions"
    assert data["filename"] == "transactions.csv"
    assert data["domain"] == "finance"
    assert data["rows_count"] == 5
    assert data["columns_count"] == 4
    assert "schema_json" in data or "schema_metadata" in data

    # 2. Verify physical path is NOT exposed in API response
    response_keys = list(data.keys())
    assert "storage_path" not in response_keys
    assert "file_path" not in response_keys
    assert "duckdb_path" not in response_keys

    # 3. Retrieve dataset metadata from GET /datasets/{id}
    detail_res = client.get(f"/datasets/{dataset_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["rows_count"] == 5
    assert detail["columns_count"] == 4

    # 4. Verify DuckDB analytical table exists
    assert dataset_table_exists(dataset_id) is True

    # 5. Verify row count directly in DuckDB
    duckdb_count = get_dataset_row_count(dataset_id)
    assert duckdb_count == 5

    # 6. Verify DuckDB columns and types
    cols = get_dataset_columns(dataset_id)
    col_names = [c[0] for c in cols]
    assert "transaction_id" in col_names
    assert "customer_name" in col_names
    assert "amount" in col_names
    assert "is_flagged" in col_names

    # 7. Verify actual rows are queryable
    rows = get_dataset_rows(dataset_id, limit=10)
    assert len(rows) == 5
    assert rows[0]["customer_name"] == "Alice"

    # 8. Verify physical file is persisted on disk
    expected_file = os.path.join(settings.DATASETS_STORAGE_DIR, f"{dataset_id}.csv")
    assert os.path.exists(expected_file)


def test_empty_csv_upload_rejected(client, auth_header):
    files = {"file": ("empty.csv", "", "text/csv")}
    upload_res = client.post("/datasets/upload", headers=auth_header, files=files)
    assert upload_res.status_code == 422
    assert "empty" in upload_res.json()["detail"].lower()


def test_csv_with_no_data_rows_rejected(client, auth_header):
    header_only_csv = "col1,col2,col3\n"
    files = {"file": ("header_only.csv", header_only_csv, "text/csv")}
    upload_res = client.post("/datasets/upload", headers=auth_header, files=files)
    assert upload_res.status_code == 422
    assert "at least one data row" in upload_res.json()["detail"].lower()


def test_non_csv_extension_rejected(client, auth_header):
    files = {"file": ("data.json", '{"key": "value"}', "application/json")}
    upload_res = client.post("/datasets/upload", headers=auth_header, files=files)
    assert upload_res.status_code == 400
    assert "only csv files" in upload_res.json()["detail"].lower()


def test_duplicate_column_names_handling(client, auth_header):
    # CSV with duplicate column headers: score and score
    dup_csv = (
        "id,score,score,name\n"
        "1,85,90,Alice\n"
        "2,72,78,Bob\n"
        "3,95,92,Charlie\n"
    )
    files = {"file": ("dup_cols.csv", dup_csv, "text/csv")}
    res = client.post(
        "/datasets/upload",
        headers=auth_header,
        files=files,
        data={"domain": "technology", "name": "Duplicate Columns Test"}
    )
    assert res.status_code == 201
    dataset_id = res.json()["id"]

    # Verify DuckDB persisted all rows and columns
    assert get_dataset_row_count(dataset_id) == 3
    cols = get_dataset_columns(dataset_id)
    col_names = [c[0] for c in cols]
    # Check that duplicates were disambiguated
    assert len(col_names) == 4
    assert len(set(col_names)) == 4
    assert "score" in col_names
    assert "score_1" in col_names


def test_unsafe_column_names_handling(client, auth_header):
    # Headers containing spaces, special characters, and SQL-like punctuation
    unsafe_csv = (
        "user id, price $, status; DROP TABLE--\n"
        "1, 19.99, active\n"
        "2, 49.99, pending\n"
    )
    files = {"file": ("unsafe.csv", unsafe_csv, "text/csv")}
    res = client.post(
        "/datasets/upload",
        headers=auth_header,
        files=files,
        data={"domain": "ecommerce", "name": "Unsafe Columns Test"}
    )
    assert res.status_code == 201
    dataset_id = res.json()["id"]

    # Verify DuckDB ingested table cleanly
    assert dataset_table_exists(dataset_id) is True
    assert get_dataset_row_count(dataset_id) == 2

    # Querying rows works without SQL syntax error
    rows = get_dataset_rows(dataset_id, limit=5)
    assert len(rows) == 2


def test_dataset_owner_relationship_preserved(client, auth_header):
    csv_data = "colA,colB\nval1,val2\nval3,val4\n"
    files = {"file": ("relationship.csv", csv_data, "text/csv")}
    res = client.post("/datasets/upload", headers=auth_header, files=files)
    assert res.status_code == 201
    dataset_id = res.json()["id"]
    user_id = res.json()["user_id"]

    # Check SQLite relationship
    sqlite_conn = get_db_connection()
    row = sqlite_conn.execute("SELECT user_id FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    assert row is not None
    assert row["user_id"] == user_id

    # Check DuckDB registry relationship
    duckdb_conn = get_duckdb_connection()
    reg = duckdb_conn.execute("SELECT user_id FROM _dataset_registry WHERE dataset_id = ?", [dataset_id]).fetchone()
    assert reg is not None
    assert reg[0] == user_id
