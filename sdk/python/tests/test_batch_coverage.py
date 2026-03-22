"""Tests for batch.py coverage gaps — auto-register, upload, run_batch, retry, scheduler."""
import json
import threading
import time
import pytest
from unittest.mock import patch, MagicMock, call
from io import BytesIO


# ─── _ensure_agent_registered ────────────────────────────────────────────────

class TestEnsureAgentRegistered:
    def _make_identity(self):
        return {"did": "did:ecp:abc123", "pub_key": "deadbeef"}

    def test_skips_if_already_registered(self, tmp_path, monkeypatch):
        import atlast_ecp.batch as batch_mod
        monkeypatch.setattr(batch_mod, "ECP_DIR", tmp_path / ".ecp")
        monkeypatch.setattr(batch_mod, "BATCH_STATE_FILE", tmp_path / ".ecp" / "batch_state.json")
        (tmp_path / ".ecp").mkdir()
        (tmp_path / ".ecp" / "batch_state.json").write_text(json.dumps({"agent_registered": True}))

        from atlast_ecp.batch import _ensure_agent_registered
        result = _ensure_agent_registered(self._make_identity())
        assert result is True

    def test_registers_successfully(self, tmp_path, monkeypatch):
        import atlast_ecp.batch as batch_mod
        monkeypatch.setattr(batch_mod, "ECP_DIR", tmp_path / ".ecp")
        monkeypatch.setattr(batch_mod, "BATCH_STATE_FILE", tmp_path / ".ecp" / "batch_state.json")

        response_data = json.dumps({
            "agent_api_key": "my-api-key",
            "claim_url": "https://claim.example.com",
            "verification_tweet": "tweet text",
        }).encode()

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch("atlast_ecp.batch.save_config") as mock_save:
                from atlast_ecp.batch import _ensure_agent_registered
                result = _ensure_agent_registered(self._make_identity())

        assert result is True
        mock_save.assert_called_once()

    def test_handles_exception_optimistically(self, tmp_path, monkeypatch):
        import atlast_ecp.batch as batch_mod
        monkeypatch.setattr(batch_mod, "ECP_DIR", tmp_path / ".ecp")
        monkeypatch.setattr(batch_mod, "BATCH_STATE_FILE", tmp_path / ".ecp" / "batch_state.json")

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            from atlast_ecp.batch import _ensure_agent_registered
            result = _ensure_agent_registered(self._make_identity())

        # Optimistic: marks registered=True anyway to avoid blocking
        assert result is False

    def test_no_save_config_if_no_api_key(self, tmp_path, monkeypatch):
        import atlast_ecp.batch as batch_mod
        monkeypatch.setattr(batch_mod, "ECP_DIR", tmp_path / ".ecp")
        monkeypatch.setattr(batch_mod, "BATCH_STATE_FILE", tmp_path / ".ecp" / "batch_state.json")

        response_data = json.dumps({"claim_url": "https://claim.example.com"}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch("atlast_ecp.batch.save_config") as mock_save:
                from atlast_ecp.batch import _ensure_agent_registered
                _ensure_agent_registered(self._make_identity())
        mock_save.assert_not_called()


# ─── upload_merkle_root ───────────────────────────────────────────────────────

class TestUploadMerkleRoot:
    def test_returns_attestation_uid_on_success(self):
        response_data = json.dumps({"attestation_uid": "uid-123"}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            from atlast_ecp.batch import upload_merkle_root
            result = upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:abc",
                record_count=5,
                avg_latency_ms=100,
                batch_ts=1000000,
                sig="ed25519:deadbeef",
            )
        assert result == "uid-123"

    def test_returns_batch_id_fallback(self):
        response_data = json.dumps({"batch_id": "batch-456"}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            from atlast_ecp.batch import upload_merkle_root
            result = upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:abc",
                record_count=1,
                avg_latency_ms=50,
                batch_ts=999,
                sig="unverified",
            )
        assert result == "batch-456"

    def test_returns_none_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            from atlast_ecp.batch import upload_merkle_root
            result = upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:abc",
                record_count=1,
                avg_latency_ms=0,
                batch_ts=999,
                sig="unverified",
            )
        assert result is None

    def test_sends_api_key_header(self):
        response_data = json.dumps({"attestation_uid": "uid-789"}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        captured_req = []
        def capture_urlopen(req, timeout=None):
            captured_req.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=capture_urlopen):
            from atlast_ecp.batch import upload_merkle_root
            upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:abc",
                record_count=1,
                avg_latency_ms=0,
                batch_ts=999,
                sig="unverified",
                agent_api_key="my-secret-key",
            )
        assert captured_req[0].get_header("X-agent-key") == "my-secret-key"

    def test_includes_optional_fields(self):
        response_data = json.dumps({"attestation_uid": "uid-opt"}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        captured_bodies = []
        def capture_urlopen(req, timeout=None):
            captured_bodies.append(json.loads(req.data))
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=capture_urlopen):
            from atlast_ecp.batch import upload_merkle_root
            upload_merkle_root(
                merkle_root="sha256:abc",
                agent_did="did:ecp:abc",
                record_count=2,
                avg_latency_ms=100,
                batch_ts=999,
                sig="unverified",
                record_hashes=[{"id": "rec_1", "hash": "sha256:h1", "flags": []}],
                flag_counts={"pii_detected": 1},
            )
        body = captured_bodies[0]
        assert "record_hashes" in body
        assert "flag_counts" in body
        assert body["flag_counts"] == {"pii_detected": 1}


# ─── run_batch ────────────────────────────────────────────────────────────────

class TestRunBatch:
    def _setup_batch_dir(self, tmp_path, monkeypatch):
        import atlast_ecp.batch as batch_mod
        ecp = tmp_path / ".ecp"
        ecp.mkdir()
        monkeypatch.setattr(batch_mod, "ECP_DIR", ecp)
        monkeypatch.setattr(batch_mod, "BATCH_STATE_FILE", ecp / "batch_state.json")

    def test_returns_empty_when_no_records(self, tmp_path, monkeypatch):
        self._setup_batch_dir(tmp_path, monkeypatch)
        with patch("atlast_ecp.batch.collect_batch", return_value=([], [])):
            from atlast_ecp.batch import run_batch
            result = run_batch()
        assert result["status"] == "empty"
        assert result["record_count"] == 0

    def test_successful_upload(self, tmp_path, monkeypatch):
        self._setup_batch_dir(tmp_path, monkeypatch)
        records = [{"id": "rec_1", "chain": {"hash": "sha256:abc"}, "step": {"latency_ms": 100, "flags": []}, "ts": 1000}]
        hashes = ["sha256:abc"]

        with patch("atlast_ecp.batch.collect_batch", return_value=(records, hashes)), \
             patch("atlast_ecp.batch.get_or_create_identity", return_value={"did": "did:ecp:test", "pub_key": "aa", "priv_key": "bb"}), \
             patch("atlast_ecp.batch.sign_data", return_value="ed25519:sig"), \
             patch("atlast_ecp.batch._ensure_agent_registered", return_value=True), \
             patch("atlast_ecp.batch._retry_queued"), \
             patch("atlast_ecp.batch.upload_merkle_root", return_value="uid-success"):
            from atlast_ecp.batch import run_batch
            result = run_batch()

        assert result["status"] == "ok"
        assert result["uploaded"] is True
        assert result["attestation_uid"] == "uid-success"

    def test_queues_on_upload_failure(self, tmp_path, monkeypatch):
        self._setup_batch_dir(tmp_path, monkeypatch)
        records = [{"id": "rec_1", "chain": {"hash": "sha256:abc"}, "step": {"latency_ms": 50, "flags": []}, "ts": 1000}]
        hashes = ["sha256:abc"]

        with patch("atlast_ecp.batch.collect_batch", return_value=(records, hashes)), \
             patch("atlast_ecp.batch.get_or_create_identity", return_value={"did": "did:ecp:test", "pub_key": "aa", "priv_key": "bb"}), \
             patch("atlast_ecp.batch.sign_data", return_value="unverified"), \
             patch("atlast_ecp.batch._ensure_agent_registered", return_value=False), \
             patch("atlast_ecp.batch._retry_queued"), \
             patch("atlast_ecp.batch.upload_merkle_root", return_value=None), \
             patch("atlast_ecp.batch.enqueue_for_upload") as mock_enqueue:
            from atlast_ecp.batch import run_batch
            result = run_batch()

        assert result["uploaded"] is False
        assert result["queued"] is True
        mock_enqueue.assert_called_once()

    def test_returns_error_on_exception(self, tmp_path, monkeypatch):
        self._setup_batch_dir(tmp_path, monkeypatch)
        with patch("atlast_ecp.batch.collect_batch", side_effect=RuntimeError("boom")):
            from atlast_ecp.batch import run_batch
            result = run_batch()
        assert result["status"] == "error"

    def test_zero_latency_when_no_latency_records(self, tmp_path, monkeypatch):
        self._setup_batch_dir(tmp_path, monkeypatch)
        records = [{"id": "rec_1", "chain": {"hash": "sha256:abc"}, "step": {"flags": []}, "ts": 1000}]
        hashes = ["sha256:abc"]

        with patch("atlast_ecp.batch.collect_batch", return_value=(records, hashes)), \
             patch("atlast_ecp.batch.get_or_create_identity", return_value={"did": "did:ecp:test", "pub_key": "aa", "priv_key": "bb"}), \
             patch("atlast_ecp.batch.sign_data", return_value="unverified"), \
             patch("atlast_ecp.batch._ensure_agent_registered", return_value=True), \
             patch("atlast_ecp.batch._retry_queued"), \
             patch("atlast_ecp.batch.upload_merkle_root", return_value="uid-ok"):
            from atlast_ecp.batch import run_batch
            result = run_batch()
        assert result["avg_latency_ms"] == 0


# ─── _retry_queued ────────────────────────────────────────────────────────────

class TestRetryQueued:
    def test_does_nothing_with_empty_queue(self):
        with patch("atlast_ecp.batch.get_upload_queue", return_value=[]):
            from atlast_ecp.batch import _retry_queued
            _retry_queued()  # should not raise

    def test_retries_and_clears_on_all_success(self):
        queue = [
            {"merkle_root": "sha256:a", "agent_did": "did:ecp:x", "record_count": 1,
             "avg_latency_ms": 0, "batch_ts": 1000, "sig": "unverified", "ecp_version": "0.1"},
            {"merkle_root": "sha256:b", "agent_did": "did:ecp:x", "record_count": 1,
             "avg_latency_ms": 0, "batch_ts": 2000, "sig": "unverified", "ecp_version": "0.1"},
        ]
        with patch("atlast_ecp.batch.get_upload_queue", return_value=queue), \
             patch("atlast_ecp.batch.upload_merkle_root", return_value="uid-ok"), \
             patch("atlast_ecp.batch.clear_upload_queue") as mock_clear:
            from atlast_ecp.batch import _retry_queued
            _retry_queued()
        mock_clear.assert_called_once()

    def test_does_not_clear_on_partial_failure(self):
        queue = [
            {"merkle_root": "sha256:a", "agent_did": "did:ecp:x", "record_count": 1,
             "avg_latency_ms": 0, "batch_ts": 1000, "sig": "unverified"},
            {"merkle_root": "sha256:b", "agent_did": "did:ecp:x", "record_count": 1,
             "avg_latency_ms": 0, "batch_ts": 2000, "sig": "unverified"},
        ]
        # First succeeds, second fails
        with patch("atlast_ecp.batch.get_upload_queue", return_value=queue), \
             patch("atlast_ecp.batch.upload_merkle_root", side_effect=["uid-ok", None]), \
             patch("atlast_ecp.batch.clear_upload_queue") as mock_clear:
            from atlast_ecp.batch import _retry_queued
            _retry_queued()
        mock_clear.assert_not_called()


# ─── start_scheduler / trigger_batch_upload ───────────────────────────────────

class TestScheduler:
    def test_start_scheduler_creates_timer(self):
        """start_scheduler should not raise and should create a background timer."""
        created_timers = []
        original_Timer = threading.Timer

        def mock_timer(interval, fn, *a, **kw):
            t = original_Timer(interval, fn, *a, **kw)
            created_timers.append(t)
            return t

        with patch("atlast_ecp.batch.threading.Timer", side_effect=mock_timer):
            from atlast_ecp.batch import start_scheduler
            start_scheduler(interval_seconds=9999)

        assert len(created_timers) >= 1
        # Clean up — cancel the timer so it doesn't fire
        for t in created_timers:
            t.cancel()

    def test_trigger_batch_upload_starts_thread(self):
        called = threading.Event()

        def fake_run_batch(flush=False):
            called.set()

        with patch("atlast_ecp.batch.run_batch", side_effect=fake_run_batch):
            from atlast_ecp.batch import trigger_batch_upload
            trigger_batch_upload(flush=True)
            called.wait(timeout=2)

        assert called.is_set()


# ─── State management ────────────────────────────────────────────────────────

class TestBatchState:
    def test_load_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        import atlast_ecp.batch as batch_mod
        monkeypatch.setattr(batch_mod, "BATCH_STATE_FILE", tmp_path / "nonexistent.json")
        from atlast_ecp.batch import _load_batch_state
        assert _load_batch_state() == {}

    def test_load_returns_empty_on_invalid_json(self, tmp_path, monkeypatch):
        import atlast_ecp.batch as batch_mod
        bad = tmp_path / "batch_state.json"
        bad.write_text("{{invalid")
        monkeypatch.setattr(batch_mod, "BATCH_STATE_FILE", bad)
        from atlast_ecp.batch import _load_batch_state
        assert _load_batch_state() == {}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        import atlast_ecp.batch as batch_mod
        ecp = tmp_path / ".ecp"
        monkeypatch.setattr(batch_mod, "ECP_DIR", ecp)
        monkeypatch.setattr(batch_mod, "BATCH_STATE_FILE", ecp / "batch_state.json")
        from atlast_ecp.batch import _save_batch_state, _load_batch_state
        state = {"last_batch_ts": 12345, "total_batches": 3}
        _save_batch_state(state)
        loaded = _load_batch_state()
        assert loaded["last_batch_ts"] == 12345
        assert loaded["total_batches"] == 3
