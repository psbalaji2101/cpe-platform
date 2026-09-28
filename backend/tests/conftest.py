import os
import tempfile
from pathlib import Path
import sys
os.environ["CPE_DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
os.environ["CPE_DATA_DIR"] = tempfile.mkdtemp(prefix="cpe-test-")
os.environ["CPE_ADMIN_PASSWORD"] = "Test-password-123456789"
os.environ["CPE_LLM_PROVIDER"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import pytest
from fastapi.testclient import TestClient
from cpe.db import Base, engine
from cpe.bootstrap import bootstrap
from cpe.api import app


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        result = client.post("/api/auth/login", json={"email":"admin@cpe.local", "password":"Test-password-123456789"})
        assert result.status_code == 200
        client.headers["X-CSRF-Token"] = result.json()["csrf"]
        yield client
