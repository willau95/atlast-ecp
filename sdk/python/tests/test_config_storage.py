"""
Tests for config and storage modules — covering edge cases to boost coverage.
"""

import os
import json
import tempfile

import pytest

from atlast_ecp.core import reset


@pytest.fixture(autouse=True)
def clean_ecp(tmp_path):
    d = str(tmp_path / "ecp")
    old_dir = os.environ.get("ATLAST_ECP_DIR")
    old_url = os.environ.get("ATLAST_API_URL")
    old_key = os.environ.get("ATLAST_API_KEY")
    os.environ["ATLAST_ECP_DIR"] = d
    os.environ.pop("ATLAST_API_URL", None)
    os.environ.pop("ATLAST_API_KEY", None)
    reset()
    yield d
    if old_dir:
        os.environ["ATLAST_ECP_DIR"] = old_dir
    else:
        os.environ.pop("ATLAST_ECP_DIR", None)
    if old_url:
        os.environ["ATLAST_API_URL"] = old_url
    if old_key:
        os.environ["ATLAST_API_KEY"] = old_key


class TestConfig:
    def test_get_api_url_from_env(self):
        from atlast_ecp.config import get_api_url
        os.environ["ATLAST_API_URL"] = "https://test.example.com/v1"
        url = get_api_url()
        assert url == "https://test.example.com/v1"

    def test_get_api_url_default(self):
        from atlast_ecp.config import get_api_url
        os.environ.pop("ATLAST_API_URL", None)
        url = get_api_url()
        # Should return empty or default
        assert isinstance(url, str)

    def test_get_api_key_from_env(self):
        from atlast_ecp.config import get_api_key
        os.environ["ATLAST_API_KEY"] = "test-key-123"
        key = get_api_key()
        assert key == "test-key-123"

    def test_load_save_config(self):
        from atlast_ecp.config import load_config, save_config
        config = load_config()
        assert isinstance(config, dict)

        config["test_value"] = "hello"
        save_config(config)

        config2 = load_config()
        assert config2.get("test_value") == "hello"


class TestStorage:
    def test_save_and_load_records(self):
        from atlast_ecp.core import record_minimal
        from atlast_ecp.storage import load_records

        record_minimal("hello", "world", agent="test")
        records = load_records(limit=5)
        assert len(records) >= 1
        assert records[-1]["agent"] == "test"

    def test_load_records_limit(self):
        from atlast_ecp.core import record_minimal
        from atlast_ecp.storage import load_records

        for i in range(10):
            record_minimal(f"p{i}", f"r{i}", agent="test")

        records = load_records(limit=3)
        assert len(records) == 3

    def test_load_record_by_id(self):
        from atlast_ecp.core import record_minimal
        from atlast_ecp.storage import load_records, load_record_by_id

        rid = record_minimal("hello", "world", agent="test")
        if rid:
            rec = load_record_by_id(rid)
            assert rec is not None
            assert rec["id"] == rid

    def test_load_record_by_id_not_found(self):
        from atlast_ecp.storage import load_record_by_id
        rec = load_record_by_id("rec_nonexistent_id")
        assert rec is None


class TestIdentity:
    def test_get_or_create_identity(self):
        from atlast_ecp.identity import get_or_create_identity
        identity = get_or_create_identity()
        assert identity is not None
        assert "did" in identity
        assert identity["did"].startswith("did:ecp:")

    def test_identity_persistence(self):
        from atlast_ecp.identity import get_or_create_identity
        id1 = get_or_create_identity()
        id2 = get_or_create_identity()
        assert id1["did"] == id2["did"]  # Same DID on repeated calls
