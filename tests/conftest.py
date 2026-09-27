import os
import tempfile
from pathlib import Path

_state = tempfile.TemporaryDirectory(prefix="nimo-tests-")
os.environ["NIMO_DATA"] = _state.name
os.environ["NIMO_DEV"] = "1"
os.environ["NIMO_ORIGIN"] = "http://testserver"
os.environ["NIMO_FREE_RESERVE"] = "0"

import pytest
from app.cli import initialize
from app.db import engine, Base, transaction
from app.models import *
from fastapi.testclient import TestClient
from app.main import app

def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    tempfile.tempdir = None
    _state.cleanup()

@pytest.fixture(autouse=True)
def database():
    initialize("test-password-123")
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())

@pytest.fixture
def client():
    import re
    with TestClient(app) as client:
        html = client.get("/login").text
        csrf = re.search(r'name="csrf" value="([^"]+)"', html)[1]
        response = client.post("/login", data={"csrf":csrf,"password":"test-password-123"}, follow_redirects=False)
        assert response.status_code == 303
        with transaction() as session:
            token = session.query(LoginSession).one().csrf
        client.csrf = token
        yield client
