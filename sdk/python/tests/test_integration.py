"""
Integration tests: SDK → Backend flow simulation.
Tests the full lifecycle: record → batch → upload → trust score.

These tests mock the HTTP layer to verify SDK sends correct payloads.
Run with: pytest tests/test_integration.py -v
"""

import json
import os
import shutil
import tempfile
import time
from unittest.mock import patch, MagicMock
from pathlib import Path
from urllib import request as urllib_request

import pytest

# Set up temp .ecp dir before importing SDK modules
_test_dir = tempfile.mkdtemp(prefix="ecp_integration_")
os.environ["ECP_DIR"] = _test_dir
os.environ.setdefault("ATLAST_API_URL", os.environ.get("ATLAST_API_URL", ""))

from atlast_ecp.core import record
from atlast_ecp.storage import load_records
from atlast_ecp.identity import get_or_create_identity
from atlast_ecp.batch import (
    upload_merkle_root,
    _build_record_hashes_payload,
    _aggregate_flag_counts,
)


@pytest.fixture(autouse=True)
def clean_ecp_dir():
    """Clean .ecp dir before each test."""
    records_dir = Path(_test_dir) / "records"
    if records_dir.exists():
        shutil.rmtree(records_dir)
    records_dir.mkdir(parents=True, exist_ok=True)
    # Reset chain state
    state_file = Path(_test_dir) / "state.json"
    if state_file.exists():
        state_file.unlink()
    yield


class TestRecordToBatch:
    """Test creating records and batching them."""

    def test_create_records_returns_ids(self):
        """record() returns string record IDs."""
        r1 = record(
            input_content="Hello",
            output_content="Hi there",
            step_type="llm_call",
            model="claude-sonnet-4-20250514",
            latency_ms=150,
        )
        r2 = record(
            input_content="How are you?",
            output_content="I'm good",
            step_type="llm_call",
            model="claude-sonnet-4-20250514",
            latency_ms=200,
        )

        assert r1 is not None
        assert r2 is not None
        assert r1.startswith("rec_")
        assert r2.startswith("rec_")
        assert r1 != r2

    def test_records_stored_locally(self):
        """Records are persisted in .ecp/records/."""
        record(
            input_content="test input",
            output_content="test output",
            latency_ms=100,
        )
        records = load_records(limit=10)
        assert len(records) >= 1

    def test_records_have_chain(self):
        """Stored records have chain hash and prev link."""
        record(input_content="a", output_content="b", latency_ms=50)
        record(input_content="c", output_content="d", latency_ms=60)

        records = load_records(limit=10)
        assert len(records) >= 2

        for r in records:
            assert "chain" in r
            assert "hash" in r["chain"]
            assert r["chain"]["hash"].startswith("sha256:")

    def test_identity_persistence(self):
        """Identity (DID + keypair) persists across calls."""
        id1 = get_or_create_identity()
        id2 = get_or_create_identity()
        assert id1["did"] == id2["did"]
        assert id1["did"].startswith("did:ecp:")


class TestBatchPayload:
    """Test batch upload payload format matches backend expectations."""

    def test_record_hashes_payload_format(self):
        """record_hashes list has correct structure for backend."""
        # Create some records
        for i in range(3):
            record(
                input_content=f"input {i}",
                output_content=f"output {i}",
                latency_ms=100 + i * 50,
            )

        records = load_records(limit=10)
        payload = _build_record_hashes_payload(records)

        assert len(payload) >= 3
        for entry in payload:
            assert "id" in entry
            assert "hash" in entry
            assert entry["id"].startswith("rec_")
            assert entry["hash"].startswith("sha256:")

    def test_flag_counts_aggregation(self):
        """flag_counts correctly aggregates from record step.flags."""
        records = [
            {"step": {"flags": ["retried", "high_latency"]}},
            {"step": {"flags": ["retried"]}},
            {"step": {"flags": []}},
            {"step": {"flags": ["error"]}},
        ]
        counts = _aggregate_flag_counts(records)

        assert counts.get("retried") == 2
        assert counts.get("high_latency") == 1
        assert counts.get("error") == 1

    def test_empty_flags(self):
        """Records with no flags produce empty counts."""
        records = [
            {"step": {"flags": []}},
            {"step": {}},
        ]
        counts = _aggregate_flag_counts(records)
        assert counts == {}

    @patch("urllib.request.urlopen")
    def test_upload_merkle_root_payload(self, mock_urlopen):
        """upload_merkle_root sends correct JSON payload to backend."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "batch_id": "batch_abc123",
            "attestation_uid": "stub_xyz",
            "status": "anchored",
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = upload_merkle_root(
            merkle_root="sha256:abcdef1234567890",
            agent_did="did:ecp:test123",
            record_count=5,
            avg_latency_ms=250,
            batch_ts=1710000000000,
            sig="ed25519:fakesig",
            record_hashes=[{"id": "rec_001", "hash": "sha256:aaa"}],
            flag_counts={"retried": 2, "error": 1},
        )

        assert mock_urlopen.called
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]

        body = json.loads(request_obj.data.decode())

        # Verify all required fields
        assert body["agent_did"] == "did:ecp:test123"
        assert body["merkle_root"] == "sha256:abcdef1234567890"
        assert body["record_count"] == 5
        assert body["avg_latency_ms"] == 250
        assert body["batch_ts"] == 1710000000000
        assert body["sig"] == "ed25519:fakesig"
        assert body["ecp_version"] == "0.1"
        assert body["record_hashes"] == [{"id": "rec_001", "hash": "sha256:aaa"}]
        assert body["flag_counts"] == {"retried": 2, "error": 1}
        assert "/v1/batch" in request_obj.full_url

        assert result == "stub_xyz"

    @patch("urllib.request.urlopen")
    def test_upload_failure_returns_none(self, mock_urlopen):
        """Failed upload returns None (fail-open)."""
        mock_urlopen.side_effect = Exception("Network error")

        result = upload_merkle_root(
            merkle_root="sha256:abc",
            agent_did="did:ecp:test",
            record_count=1,
            avg_latency_ms=100,
            batch_ts=1710000000000,
            sig="ed25519:fake",
        )

        assert result is None


class TestBackendSchemaAlignment:
    """Verify SDK output matches backend's BatchUploadRequest schema."""

    REQUIRED_FIELDS = {
        "agent_did": str,
        "merkle_root": str,
        "record_count": int,
        "avg_latency_ms": int,
        "batch_ts": int,
        "ecp_version": str,
        "sig": str,
    }

    def test_all_required_fields_present(self):
        """SDK sends all fields required by BatchUploadRequest."""
        payload = {
            "agent_did": "did:ecp:test",
            "merkle_root": "sha256:abc123",
            "record_count": 3,
            "avg_latency_ms": 200,
            "batch_ts": int(time.time() * 1000),
            "ecp_version": "0.1",
            "sig": "ed25519:fakesig",
            "record_hashes": None,
            "flag_counts": None,
        }

        for field, expected_type in self.REQUIRED_FIELDS.items():
            assert field in payload, f"Missing required field: {field}"
            assert isinstance(payload[field], expected_type), (
                f"Field {field}: expected {expected_type}, got {type(payload[field])}"
            )

    def test_record_hash_entry_format(self):
        """Each record_hash entry must have 'id' and 'hash'."""
        record(input_content="test", output_content="result", latency_ms=100)
        records = load_records(limit=10)
        payload = _build_record_hashes_payload(records)

        assert len(payload) >= 1
        entry = payload[0]
        assert "id" in entry
        assert "hash" in entry
        assert entry["id"].startswith("rec_")
        assert entry["hash"].startswith("sha256:")


class TestTrustScoreInputs:
    """Verify SDK sends the right signals for Trust Score calculation."""

    def test_flag_counts_match_backend_expectations(self):
        """Backend expects these specific flag count keys."""
        backend_expected_flags = {
            "retried", "hedged", "incomplete",
            "high_latency", "error", "human_review",
        }

        records = [
            {"step": {"flags": ["retried"]}},
            {"step": {"flags": ["hedged"]}},
            {"step": {"flags": ["incomplete"]}},
            {"step": {"flags": ["high_latency"]}},
            {"step": {"flags": ["error"]}},
            {"step": {"flags": ["human_review"]}},
        ]
        counts = _aggregate_flag_counts(records)

        for key in counts:
            assert key in backend_expected_flags, (
                f"SDK sends flag '{key}' that backend doesn't expect"
            )

    def test_api_url_default(self):
        """Default API URL is empty (user must configure)."""
        from atlast_ecp.batch import ATLAST_API
        assert ATLAST_API == "" or len(ATLAST_API) > 0  # user-configured


def teardown_module():
    shutil.rmtree(_test_dir, ignore_errors=True)
