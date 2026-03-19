"""Test fixtures for ECP Reference Server."""

import os
import pytest
from fastapi.testclient import TestClient

from server.config import settings


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    """Use a fresh temp database for each test."""
    db_path = str(tmp_path / "test.db")
    settings.DB_PATH = db_path

    # Reset the module-level _db connection
    from server import database
    database._db = None

    yield

    database.close_db()


@pytest.fixture
def client():
    from server.main import app
    return TestClient(app)


@pytest.fixture
def registered_agent(client):
    """Register a test agent and return its info including api_key."""
    resp = client.post("/v1/agents/register", json={
        "did": "did:ecp:test123",
        "public_key": "dGVzdC1rZXk=",
        "handle": "test-agent",
        "display_name": "Test Agent",
    })
    assert resp.status_code == 201
    return resp.json()
