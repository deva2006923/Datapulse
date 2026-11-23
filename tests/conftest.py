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
os.environ["RATE_LIMIT_ENABLED"] = "false"
# Keep unit/integration test runs deterministic and offline without burning real .env API quota
os.environ["DATABASE_URL"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["AI_FALLBACK_PROVIDER"] = ""
os.environ["AI_FALLBACK_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["R2_ENDPOINT_URL"] = ""
os.environ["R2_BUCKET_NAME"] = ""
os.environ["R2_ACCESS_KEY_ID"] = ""
os.environ["R2_SECRET_ACCESS_KEY"] = ""

from app.config import settings
settings.DATABASE_URL = None
settings.DATABASE_PATH = temp_db_path
settings.DUCKDB_PATH = temp_duckdb_path
settings.DATASETS_STORAGE_DIR = temp_datasets_dir
settings.RATE_LIMIT_ENABLED = False
settings.GEMINI_API_KEY = None
settings.AI_FALLBACK_PROVIDER = None
settings.AI_FALLBACK_API_KEY = None
settings.GROQ_API_KEY = None
settings.R2_ENDPOINT_URL = None
settings.R2_BUCKET_NAME = None
settings.R2_ACCESS_KEY_ID = None
settings.R2_SECRET_ACCESS_KEY = None

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
