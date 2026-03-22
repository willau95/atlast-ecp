"""Tests for batch.py upload and batch processing functions."""
import json
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest
from atlast_ecp.batch import (
    upload_merkle_root,
    run_batch,
    start_scheduler,
    trigger_batch_upload,
    _ensure_agent_registered,
    _retry_queued,
    _load_batch_state,
    _save_batch_state,
    MIN_BATCH_INTERVAL_S,
    MAX_RECORDS_PER_BATCH,
)


class TestUploadMerkleRoot:
    def test_success_returns_uid(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"attestation_uid": "att_123"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("atlast_ecp.batch.urllib.request.urlopen", return_value=mock_resp):
            uid = upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:test",
                record_count=5,
                avg_latency_ms=100,
                batch_ts=int(time.time() * 1000),
                sig="ed25519:abc",
            )
        assert uid == "att_123"

    def test_failure_returns_none(self):
        with patch("atlast_ecp.batch.urllib.request.urlopen", side_effect=Exception("network")):
            uid = upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:test",
                record_count=5,
                avg_latency_ms=100,
                batch_ts=int(time.time() * 1000),
                sig="ed25519:abc",
            )
        assert uid is None

    def test_with_api_key_sets_header(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"batch_id": "b_1"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("atlast_ecp.batch.urllib.request.urlopen", return_value=mock_resp) as mock_url:
            upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:test",
                record_count=1,
                avg_latency_ms=0,
                batch_ts=1000,
                sig="unverified",
                agent_api_key="ak_live_test",
            )
            req = mock_url.call_args[0][0]
            assert req.get_header("X-agent-key") == "ak_live_test"

    def test_with_record_hashes_and_flags(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"attestation_uid": "att_x"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("atlast_ecp.batch.urllib.request.urlopen", return_value=mock_resp) as mock_url:
            uid = upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:test",
                record_count=2,
                avg_latency_ms=50,
                batch_ts=2000,
                sig="ed25519:xyz",
                record_hashes=[{"id": "rec_1", "hash": "sha256:a", "flags": []}],
                flag_counts={"error": 1},
            )
        assert uid == "att_x"
        sent_body = json.loads(mock_url.call_args[0][0].data)
        assert sent_body["flag_counts"] == {"error": 1}
        assert len(sent_body["record_hashes"]) == 1


class TestEnsureAgentRegistered:
    def test_already_registered(self, tmp_path):
        state_file = tmp_path / "batch_state.json"
        state_file.write_text(json.dumps({"agent_registered": True}))

        with patch("atlast_ecp.batch.BATCH_STATE_FILE", state_file):
            result = _ensure_agent_registered({"did": "did:ecp:x", "pub_key": "pk"})
        assert result is True

    def test_registration_failure_sets_optimistic(self, tmp_path):
        state_file = tmp_path / "batch_state.json"
        state_file.write_text("{}")
        ecp_dir = tmp_path

        with patch("atlast_ecp.batch.BATCH_STATE_FILE", state_file), \
             patch("atlast_ecp.batch.ECP_DIR", ecp_dir), \
             patch("atlast_ecp.batch.urllib.request.urlopen", side_effect=Exception("fail")):
            result = _ensure_agent_registered({"did": "did:ecp:x", "pub_key": "pk"})
        assert result is False
        state = json.loads(state_file.read_text())
        assert state["agent_registered"] is True  # optimistic


class TestRunBatch:
    def test_empty_batch(self, tmp_path):
        state_file = tmp_path / "batch_state.json"
        state_file.write_text("{}")

        with patch("atlast_ecp.batch.BATCH_STATE_FILE", state_file), \
             patch("atlast_ecp.batch.collect_batch", return_value=([], [])):
            result = run_batch()
        assert result["status"] == "empty"

    def test_throttled_when_too_soon(self, tmp_path):
        state_file = tmp_path / "batch_state.json"
        # Set last_batch_ts to now (should throttle)
        state_file.write_text(json.dumps({"last_batch_ts": int(time.time() * 1000)}))

        with patch("atlast_ecp.batch.BATCH_STATE_FILE", state_file):
            result = run_batch(flush=False)
        assert result["status"] == "throttled"

    def test_flush_bypasses_throttle(self, tmp_path):
        state_file = tmp_path / "batch_state.json"
        state_file.write_text(json.dumps({"last_batch_ts": int(time.time() * 1000)}))

        with patch("atlast_ecp.batch.BATCH_STATE_FILE", state_file), \
             patch("atlast_ecp.batch.collect_batch", return_value=([], [])):
            result = run_batch(flush=True)
        assert result["status"] == "empty"  # got past throttle, but no records

    def test_successful_batch(self, tmp_path):
        state_file = tmp_path / "batch_state.json"
        state_file.write_text("{}")
        ecp_dir = tmp_path

        records = [{"step": {"latency_ms": 100}}]
        hashes = ["sha256:abc123"]

        with patch("atlast_ecp.batch.BATCH_STATE_FILE", state_file), \
             patch("atlast_ecp.batch.ECP_DIR", ecp_dir), \
             patch("atlast_ecp.batch.collect_batch", return_value=(records, hashes)), \
             patch("atlast_ecp.batch.build_merkle_tree", return_value=("sha256:root", [[]])), \
             patch("atlast_ecp.batch.get_or_create_identity", return_value={"did": "did:ecp:t", "pub_key": "pk"}), \
             patch("atlast_ecp.batch.sign_data", return_value="ed25519:sig"), \
             patch("atlast_ecp.batch._ensure_agent_registered"), \
             patch("atlast_ecp.batch._retry_queued"), \
             patch("atlast_ecp.batch._build_record_hashes_payload", return_value=None), \
             patch("atlast_ecp.batch._aggregate_flag_counts", return_value=None), \
             patch("atlast_ecp.batch._get_config_api_key", return_value=None), \
             patch("atlast_ecp.batch.upload_merkle_root", return_value="att_xyz"):
            result = run_batch()
        assert result["status"] == "ok"
        assert result["uploaded"] is True
        assert result["attestation_uid"] == "att_xyz"

    def test_failed_upload_queues(self, tmp_path):
        state_file = tmp_path / "batch_state.json"
        state_file.write_text("{}")
        ecp_dir = tmp_path

        records = [{"step": {"latency_ms": 50}}]
        hashes = ["sha256:h1"]

        with patch("atlast_ecp.batch.BATCH_STATE_FILE", state_file), \
             patch("atlast_ecp.batch.ECP_DIR", ecp_dir), \
             patch("atlast_ecp.batch.collect_batch", return_value=(records, hashes)), \
             patch("atlast_ecp.batch.build_merkle_tree", return_value=("sha256:root2", [[]])), \
             patch("atlast_ecp.batch.get_or_create_identity", return_value={"did": "did:ecp:t", "pub_key": "pk"}), \
             patch("atlast_ecp.batch.sign_data", return_value="ed25519:sig"), \
             patch("atlast_ecp.batch._ensure_agent_registered"), \
             patch("atlast_ecp.batch._retry_queued"), \
             patch("atlast_ecp.batch._build_record_hashes_payload", return_value=None), \
             patch("atlast_ecp.batch._aggregate_flag_counts", return_value=None), \
             patch("atlast_ecp.batch._get_config_api_key", return_value=None), \
             patch("atlast_ecp.batch.upload_merkle_root", return_value=None), \
             patch("atlast_ecp.batch.enqueue_for_upload") as mock_enqueue:
            result = run_batch()
        assert result["uploaded"] is False
        assert result["queued"] is True
        mock_enqueue.assert_called_once()

    def test_exception_returns_error(self, tmp_path):
        state_file = tmp_path / "batch_state.json"
        state_file.write_text("{}")

        with patch("atlast_ecp.batch.BATCH_STATE_FILE", state_file), \
             patch("atlast_ecp.batch.collect_batch", side_effect=RuntimeError("boom")):
            result = run_batch()
        assert result["status"] == "error"


class TestRetryQueued:
    def test_empty_queue(self):
        with patch("atlast_ecp.batch.get_upload_queue", return_value=[]):
            _retry_queued()  # should not raise

    def test_successful_retry_clears_queue(self):
        queue = [{
            "merkle_root": "sha256:r",
            "agent_did": "did:ecp:a",
            "record_count": 1,
            "avg_latency_ms": 0,
            "batch_ts": 1000,
            "sig": "unverified",
        }]
        with patch("atlast_ecp.batch.get_upload_queue", return_value=queue), \
             patch("atlast_ecp.batch.upload_merkle_root", return_value="att_1"), \
             patch("atlast_ecp.batch.clear_upload_queue") as mock_clear:
            _retry_queued()
        mock_clear.assert_called_once()


class TestScheduler:
    def test_start_scheduler_creates_timer(self):
        import atlast_ecp.batch as b
        with patch("atlast_ecp.batch.run_batch"):
            start_scheduler(interval_seconds=9999)
            assert b._batch_timer is not None
            b._batch_timer.cancel()

    def test_trigger_batch_upload(self):
        with patch("atlast_ecp.batch.run_batch") as mock_run:
            trigger_batch_upload(flush=True)
            time.sleep(0.1)
            mock_run.assert_called_once_with(flush=True)


class TestBatchState:
    def test_load_nonexistent(self, tmp_path):
        with patch("atlast_ecp.batch.BATCH_STATE_FILE", tmp_path / "nope.json"):
            assert _load_batch_state() == {}

    def test_load_corrupt(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json{{{")
        with patch("atlast_ecp.batch.BATCH_STATE_FILE", f):
            assert _load_batch_state() == {}

    def test_save_and_load(self, tmp_path):
        f = tmp_path / "state.json"
        with patch("atlast_ecp.batch.BATCH_STATE_FILE", f), \
             patch("atlast_ecp.batch.ECP_DIR", tmp_path):
            _save_batch_state({"x": 1})
            assert _load_batch_state() == {"x": 1}
