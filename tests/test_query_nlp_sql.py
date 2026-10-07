import uuid
import pytest
from app.services.nl_query import set_ai_generator, AIProviderError
from app.services.storage import get_dataset_table_name


@pytest.fixture
def auth_header(client):
    """Fixture to create a fresh user and return Authorization header."""
    unique_email = f"nlp_tester_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post("/auth/register", json={
        "email": unique_email,
        "password": "Password123!",
        "full_name": "NLP SQL Tester"
    })
    assert res.status_code == 201
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_dataset(client, auth_header):
    """Fixture to upload a sample sales dataset and return dataset info."""
    csv_data = (
        "product,region,sales,quantity\n"
        "Laptop,North,50000,10\n"
        "Phone,South,30000,25\n"
        "Laptop,South,45000,8\n"
        "Tablet,North,20000,15\n"
        "Monitor,East,15000,12\n"
    )
    files = {"file": ("sales_data.csv", csv_data, "text/csv")}
    res = client.post(
        "/datasets/upload",
        headers=auth_header,
        files=files,
        data={"domain": "ecommerce", "name": "Company Sales"}
    )
    assert res.status_code == 201
    dataset = res.json()
    dataset_id = dataset["id"]
    table_name = get_dataset_table_name(dataset_id)
    return {
        "dataset_id": dataset_id,
        "name": dataset["name"],
        "table_name": table_name
    }


@pytest.fixture(autouse=True)
def cleanup_mock_generator():
    """Ensure mock AI generator is cleared after every test."""
    yield
    set_ai_generator(None)


# 1. Simple SELECT query
def test_simple_select_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT product, sales FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "Show products and their sales",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["method"] == "nl_to_sql"
    assert "product" in data["columns"]
    assert "sales" in data["columns"]
    assert len(data["results"]) == 5


# 2. COUNT query
def test_count_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT COUNT(*) AS total_count FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "How many sales records exist?",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["columns"] == ["total_count"]
    assert data["results"][0]["total_count"] == 5
    assert "5" in data["answer"]


# 3. SUM query
def test_sum_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT SUM(sales) AS total_sales FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "What is the total sales amount?",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["columns"] == ["total_sales"]
    assert data["results"][0]["total_sales"] == 160000
    assert "160,000" in data["answer"] or "160000" in data["answer"]


# 4. AVG query
def test_avg_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT AVG(sales) AS avg_sales FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "What is the average sales value?",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["columns"] == ["avg_sales"]
    assert data["results"][0]["avg_sales"] == 32000.0


# 5. MIN query
def test_min_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT MIN(sales) AS min_sales FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "What is the lowest sales amount?",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["results"][0]["min_sales"] == 15000


# 6. MAX query
def test_max_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT MAX(sales) AS max_sales FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "What is the highest sales amount?",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["results"][0]["max_sales"] == 50000


# 7. WHERE filtering
def test_where_filtering(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT product, sales FROM {table} WHERE sales > 35000")

    res = client.post("/query", headers=auth_header, json={
        "query": "Show sales above 35000",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 2
    for r in data["results"]:
        assert r["sales"] > 35000


# 8. GROUP BY
def test_group_by_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT region, SUM(sales) AS total_sales FROM {table} GROUP BY region ORDER BY total_sales DESC")

    res = client.post("/query", headers=auth_header, json={
        "query": "Show total sales by region",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 3
    regions = [r["region"] for r in data["results"]]
    assert "South" in regions
    assert "North" in regions


# 9. ORDER BY
def test_order_by_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT product, sales FROM {table} ORDER BY sales DESC")

    res = client.post("/query", headers=auth_header, json={
        "query": "List products sorted by sales descending",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    sales_values = [r["sales"] for r in data["results"]]
    assert sales_values == sorted(sales_values, reverse=True)


# 10. LIMIT
def test_limit_query(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT product, sales FROM {table} ORDER BY sales DESC LIMIT 2")

    res = client.post("/query", headers=auth_header, json={
        "query": "Top 2 products by sales",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 2


# 11. String filtering (ILIKE)
def test_string_filtering(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT product, region, sales FROM {table} WHERE region ILIKE 'North'")

    res = client.post("/query", headers=auth_header, json={
        "query": "Show sales in the North region",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 2
    for r in data["results"]:
        assert r["region"] == "North"


# 12. Dataset selection (automatic semantic matching)
def test_automatic_dataset_selection(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT COUNT(*) AS total_sales_count FROM {table}")

    # No dataset_id provided: system should identify Company Sales dataset
    res = client.post("/query", headers=auth_header, json={
        "query": "How many ecommerce sales records exist in company sales?"
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["matching_datasets"]) >= 1
    assert data["matching_datasets"][0] == "Company Sales"


# 13. Explicit dataset_id
def test_explicit_dataset_id(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT * FROM {table} LIMIT 1")

    res = client.post("/query", headers=auth_header, json={
        "query": "Get sample row",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    assert len(res.json()["results"]) == 1


# 14. Actual DuckDB execution
def test_actual_duckdb_execution(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT product, region, sales, quantity FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "Fetch all dataset contents",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["method"] == "nl_to_sql"
    assert data["sql_query"].startswith("SELECT")
    assert data["records_analyzed"] == 5


# 15. Actual returned rows
def test_actual_returned_rows(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT product, region, sales FROM {table} WHERE product = 'Laptop' ORDER BY sales DESC")

    res = client.post("/query", headers=auth_header, json={
        "query": "Show laptop records",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    rows = res.json()["results"]
    assert len(rows) == 2
    assert rows[0] == {"product": "Laptop", "region": "North", "sales": 50000}
    assert rows[1] == {"product": "Laptop", "region": "South", "sales": 45000}


# 16. Invalid SQL syntax rejection
def test_invalid_sql_syntax_rejected(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT * FROM {table} WHERE")

    res = client.post("/query", headers=auth_header, json={
        "query": "Syntax error test",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "syntax" in res.json()["detail"].lower() or "validation error" in res.json()["detail"].lower()


# 17. DROP rejection
def test_drop_rejection(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"DROP TABLE {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "Drop this table",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "security" in res.json()["detail"].lower() or "forbidden" in res.json()["detail"].lower()


# 18. DELETE rejection
def test_delete_rejection(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"DELETE FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "Delete all rows",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "forbidden" in res.json()["detail"].lower() or "security" in res.json()["detail"].lower()


# 19. UPDATE rejection
def test_update_rejection(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"UPDATE {table} SET sales = 0")

    res = client.post("/query", headers=auth_header, json={
        "query": "Update sales to zero",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "forbidden" in res.json()["detail"].lower() or "security" in res.json()["detail"].lower()


# 20. INSERT rejection
def test_insert_rejection(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"INSERT INTO {table} VALUES ('Fake', 'West', 100, 1)")

    res = client.post("/query", headers=auth_header, json={
        "query": "Insert a row",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "forbidden" in res.json()["detail"].lower() or "security" in res.json()["detail"].lower()


# 21. PRAGMA rejection
def test_pragma_rejection(client, auth_header, test_dataset):
    set_ai_generator(lambda q, t, cols: "PRAGMA version")

    res = client.post("/query", headers=auth_header, json={
        "query": "Show pragma version",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "forbidden" in res.json()["detail"].lower() or "security" in res.json()["detail"].lower()


# 22. Multiple statements rejection
def test_multiple_statements_rejection(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT * FROM {table}; DROP TABLE {table};")

    res = client.post("/query", headers=auth_header, json={
        "query": "Multi statement attack",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "multiple" in res.json()["detail"].lower() or "security" in res.json()["detail"].lower()


# 23. Unknown column rejection
def test_unknown_column_rejection(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT non_existent_secret_column FROM {table}")

    res = client.post("/query", headers=auth_header, json={
        "query": "Query unknown column",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "column" in res.json()["detail"].lower() or "validation" in res.json()["detail"].lower()


# 24. Unknown / unauthorized table rejection
def test_unknown_table_rejection(client, auth_header, test_dataset):
    set_ai_generator(lambda q, t, cols: "SELECT * FROM _dataset_registry")

    res = client.post("/query", headers=auth_header, json={
        "query": "Query internal registry",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 422
    assert "unauthorized table" in res.json()["detail"].lower() or "security" in res.json()["detail"].lower()


# 25. Empty result handling
def test_empty_result(client, auth_header, test_dataset):
    table = test_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT * FROM {table} WHERE sales > 99999999")

    res = client.post("/query", headers=auth_header, json={
        "query": "Find sales over 99 million",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 0
    assert "no matching records" in data["answer"].lower()


# 26. AI provider failure handling
def test_ai_provider_failure(client, auth_header, test_dataset):
    def failing_ai(q, t, cols):
        raise AIProviderError("Simulated Gemini API rate limit / connection timeout")

    set_ai_generator(failing_ai)

    res = client.post("/query", headers=auth_header, json={
        "query": "What are the sales?",
        "dataset_id": test_dataset["dataset_id"]
    })
    assert res.status_code == 503
    assert "simulated gemini api" in res.json()["detail"].lower()
