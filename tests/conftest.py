import os
import tempfile
import pytest
from starlette.testclient import TestClient

# Use temporary database and storage for tests
temp_storage_dir = tempfile.TemporaryDirectory()
temp_db_path = os.path.join(temp_storage_dir.name, "test_datapulse.db")
temp_duckdb_path = os.path.join(temp_storage_dir.name, "test_analytics.duckdb")
temp_datasets_dir = os.path.join(temp_storage_dir.name, "datasets")

os.environ["DATABASE_PATH"] = temp_db_path
os.environ["DUCKDB_PATH"] = temp_duckdb_path
os.environ["DATASETS_STORAGE_DIR"] = temp_datasets_dir
os.environ["EMBEDDINGS_ENABLED"] = "true"

from app.config import settings
settings.DATABASE_PATH = temp_db_path
settings.DUCKDB_PATH = temp_duckdb_path
settings.DATASETS_STORAGE_DIR = temp_datasets_dir

from app.main import app
from app.database import init_db
from app.services.storage import init_storage, reset_storage_connection

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
    init_storage()
    yield
    reset_storage_connection()
    try:
        temp_storage_dir.cleanup()
    except Exception:
        pass

@pytest.fixture
def client():
    return TestClient(app)
