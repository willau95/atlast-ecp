"""Shared test fixtures for ATLAST ECP tests."""
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _isolate_ecp_dir(tmp_path, monkeypatch):
    """Ensure every test uses an isolated ECP directory."""
    ecp_dir = str(tmp_path / ".ecp")
    monkeypatch.setenv("ATLAST_ECP_DIR", ecp_dir)
    # Ensure a valid API URL for tests that mock urllib (CI has no env set)
    monkeypatch.setenv("ATLAST_API_URL", "https://test.atlast.example/v1")

    import atlast_ecp.storage as _storage
    import atlast_ecp.identity as _identity

    _storage.ECP_DIR = Path(ecp_dir)
    _storage.RECORDS_DIR = _storage.ECP_DIR / "records"
    _storage.LOCAL_DIR = _storage.ECP_DIR / "local"
    _storage.INDEX_FILE = _storage.ECP_DIR / "index.json"
    _storage.QUEUE_FILE = _storage.ECP_DIR / "upload_queue.jsonl"
    _identity.ECP_DIR = Path(ecp_dir)
    _identity.IDENTITY_FILE = _identity.ECP_DIR / "identity.json"
