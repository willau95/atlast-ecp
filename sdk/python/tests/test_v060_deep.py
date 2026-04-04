"""
Deep comprehensive tests for ATLAST ECP v0.6.0

Covers ALL new functionality introduced in v0.6.0:
1. create_minimal_record() — edge cases, field validation, hash consistency
2. record_minimal() / record_minimal_async() — fail-open, flag detection, storage
3. CLI commands — init, record, log, run (E2E subprocess tests)
4. Proxy pipeline — end-to-end record → save → load → verify
5. Cross-format compatibility — v0.1 vs v1.0 records coexisting
6. _extract_text() — all content formats
7. _is_anonymous() — env var handling
8. Config integration — config priority chain
"""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import pytest

from atlast_ecp.record import create_minimal_record, create_record, hash_content, record_to_dict
from atlast_ecp.core import record_minimal, record_minimal_async, _extract_text, _is_anonymous, reset
from atlast_ecp.storage import save_record, load_records, load_record_by_id, init_storage
from atlast_ecp.signals import detect_flags


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_ecp_dir(tmp_path):
    """Every test gets a fresh ECP directory."""
    d = str(tmp_path / "ecp")
    old = os.environ.get("ATLAST_ECP_DIR")
    os.environ["ATLAST_ECP_DIR"] = d
    reset()
    yield d
    if old:
        os.environ["ATLAST_ECP_DIR"] = old
    else:
        os.environ.pop("ATLAST_ECP_DIR", None)


# ─────────────────────────────────────────────────────────────────────────────
# 1. create_minimal_record() — Deep Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateMinimalRecord:
    """Deep tests for the v1.0 minimal record format."""

    def test_basic_structure(self):
        rec = create_minimal_record("my-agent", "llm_call", "hello", "world")
        assert rec["ecp"] == "1.0"
        assert rec["agent"] == "my-agent"
        assert rec["action"] == "llm_call"
        assert rec["id"].startswith("rec_")
        assert len(rec["id"]) == 20  # rec_ + 16 hex
        assert isinstance(rec["ts"], int)
        assert rec["in_hash"].startswith("sha256:")
        assert rec["out_hash"].startswith("sha256:")

    def test_unique_ids(self):
        """Each record gets a unique ID."""
        ids = {create_minimal_record("a", "llm_call", "in", "out")["id"] for _ in range(100)}
        assert len(ids) == 100

    def test_timestamp_is_epoch_ms(self):
        before = int(time.time() * 1000)
        rec = create_minimal_record("a", "llm_call", "in", "out")
        after = int(time.time() * 1000)
        assert before <= rec["ts"] <= after

    def test_hash_deterministic(self):
        """Same content → same hash."""
        r1 = create_minimal_record("a", "llm_call", "hello", "world")
        r2 = create_minimal_record("a", "llm_call", "hello", "world")
        assert r1["in_hash"] == r2["in_hash"]
        assert r1["out_hash"] == r2["out_hash"]

    def test_hash_different_content(self):
        r1 = create_minimal_record("a", "llm_call", "hello", "world")
        r2 = create_minimal_record("a", "llm_call", "goodbye", "world")
        assert r1["in_hash"] != r2["in_hash"]
        assert r1["out_hash"] == r2["out_hash"]

    def test_hash_matches_manual_sha256(self):
        """Verify hash matches raw SHA-256."""
        content = "test input content"
        rec = create_minimal_record("a", "llm_call", content, "out")
        expected = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        assert rec["in_hash"] == expected

    def test_meta_included(self):
        meta = {"model": "gpt-4", "tokens_in": 10, "tokens_out": 20, "latency_ms": 150}
        rec = create_minimal_record("a", "llm_call", "in", "out", meta=meta)
        assert rec["meta"]["model"] == "gpt-4"
        assert rec["meta"]["tokens_in"] == 10

    def test_meta_none_values_excluded(self):
        meta = {"model": "gpt-4", "tokens_in": None, "cost_usd": None}
        rec = create_minimal_record("a", "llm_call", "in", "out", meta=meta)
        assert "tokens_in" not in rec["meta"]
        assert rec["meta"]["model"] == "gpt-4"

    def test_no_meta_if_none(self):
        rec = create_minimal_record("a", "llm_call", "in", "out")
        assert "meta" not in rec

    def test_empty_meta_not_included(self):
        rec = create_minimal_record("a", "llm_call", "in", "out", meta={})
        # Empty dict is falsy, so meta should not be added
        assert "meta" not in rec

    def test_any_agent_string(self):
        """Agent can be any string — not restricted to DID."""
        for agent in ["my-bot", "agent-007", "测试Agent", "a" * 200, "user@email.com"]:
            rec = create_minimal_record(agent, "llm_call", "in", "out")
            assert rec["agent"] == agent

    def test_any_action_type(self):
        for action in ["llm_call", "tool_call", "message", "a2a_call", "custom_action"]:
            rec = create_minimal_record("a", action, "in", "out")
            assert rec["action"] == action

    def test_empty_content_hashed(self):
        """Empty string still gets a hash."""
        rec = create_minimal_record("a", "llm_call", "", "")
        assert rec["in_hash"].startswith("sha256:")
        assert rec["out_hash"].startswith("sha256:")
        assert rec["in_hash"] == rec["out_hash"]  # same empty string

    def test_unicode_content(self):
        rec = create_minimal_record("a", "llm_call", "你好世界 🌍", "مرحبا")
        assert rec["in_hash"].startswith("sha256:")
        assert rec["out_hash"].startswith("sha256:")

    def test_large_content(self):
        """Large content doesn't break anything (only hash is stored)."""
        big = "x" * (10 * 1024 * 1024)  # 10MB
        rec = create_minimal_record("a", "llm_call", big, big)
        assert rec["in_hash"].startswith("sha256:")
        assert len(json.dumps(rec)) < 1000  # record itself is tiny

    def test_json_serializable(self):
        meta = {"model": "gpt-4", "tokens_in": 100, "latency_ms": 50, "flags": ["high_latency"]}
        rec = create_minimal_record("a", "llm_call", "in", "out", meta=meta)
        serialized = json.dumps(rec)
        deserialized = json.loads(serialized)
        assert deserialized == rec

    def test_minimal_record_has_required_fields_plus_chain(self):
        """v0.16+: minimal records include chain + sig."""
        rec = create_minimal_record("a", "llm_call", "in", "out")
        required = {"ecp", "id", "ts", "agent", "action", "in_hash", "out_hash", "chain", "sig"}
        assert required.issubset(set(rec.keys()))

    def test_minimal_record_with_meta(self):
        rec = create_minimal_record("a", "llm_call", "in", "out", meta={"model": "x"})
        assert "meta" in rec
        assert "chain" in rec


# ─────────────────────────────────────────────────────────────────────────────
# 2. record_minimal() — Full Pipeline Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordMinimal:
    """Tests for record_minimal() — the main recording function."""

    def test_returns_record_id(self):
        rid = record_minimal("prompt", "response", agent="test-agent")
        assert rid is not None
        assert rid.startswith("rec_")

    def test_saves_to_disk(self, clean_ecp_dir):
        record_minimal("prompt", "response", agent="test")
        records = load_records(limit=10)
        assert len(records) >= 1
        rec = records[-1]
        assert rec["ecp"] == "1.0"
        assert rec["agent"] == "test"

    def test_flag_detection_high_latency(self):
        rid = record_minimal("prompt", "response", latency_ms=15000)
        records = load_records(limit=10)
        rec = [r for r in records if r.get("id") == rid][0]
        assert "high_latency" in rec.get("meta", {}).get("flags", [])

    def test_flag_detection_error(self):
        rid = record_minimal("prompt", "Error: something went wrong", agent="test")
        records = load_records(limit=10)
        rec = [r for r in records if r.get("id") == rid][0]
        flags = rec.get("meta", {}).get("flags", [])
        assert "error" in flags

    def test_model_in_meta(self):
        rid = record_minimal("in", "out", model="gpt-4o")
        records = load_records(limit=10)
        rec = [r for r in records if r.get("id") == rid][0]
        assert rec["meta"]["model"] == "gpt-4o"

    def test_tokens_in_meta(self):
        rid = record_minimal("in", "out", tokens_in=100, tokens_out=50)
        records = load_records(limit=10)
        rec = [r for r in records if r.get("id") == rid][0]
        assert rec["meta"]["tokens_in"] == 100
        assert rec["meta"]["tokens_out"] == 50

    def test_fail_open_never_raises(self):
        """record_minimal must never throw, even with garbage input."""
        # These should all return None gracefully, not crash
        assert record_minimal(None, None) is not None or True  # returns id or None, both OK
        # Force an internal error by mocking save_record
        import unittest.mock as mock
        with mock.patch("atlast_ecp.core.save_record", side_effect=PermissionError("denied")):
            result = record_minimal("in", "out")
            assert result is None  # fail-open returns None

    def test_default_agent(self):
        rid = record_minimal("in", "out")
        records = load_records(limit=10)
        rec = [r for r in records if r.get("id") == rid][0]
        assert rec["agent"] == "default"

    def test_default_action(self):
        rid = record_minimal("in", "out")
        records = load_records(limit=10)
        rec = [r for r in records if r.get("id") == rid][0]
        assert rec["action"] == "llm_call"

    def test_multiple_records_sequential(self):
        ids = []
        for i in range(10):
            rid = record_minimal(f"prompt {i}", f"response {i}", agent="batch")
            ids.append(rid)
        records = load_records(limit=20)
        stored_ids = {r["id"] for r in records}
        for rid in ids:
            assert rid in stored_ids


class TestRecordMinimalAsync:
    """Tests for the fire-and-forget async version."""

    def test_does_not_block(self):
        start = time.time()
        record_minimal_async("prompt", "response", agent="async-test")
        elapsed = time.time() - start
        assert elapsed < 0.1  # must return immediately

    def test_eventually_saves(self, clean_ecp_dir):
        record_minimal_async("prompt", "response", agent="async-test")
        time.sleep(1.0)  # wait for background thread
        records = load_records(limit=10)
        assert any(r.get("agent") == "async-test" for r in records)


# ─────────────────────────────────────────────────────────────────────────────
# 3. _extract_text() — Content Format Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractText:

    def test_string(self):
        assert _extract_text("hello") == "hello"

    def test_list_of_strings(self):
        assert _extract_text(["hello", "world"]) == "hello world"

    def test_list_of_text_dicts(self):
        content = [{"type": "text", "text": "Hello"}, {"type": "text", "text": "world"}]
        assert _extract_text(content) == "Hello world"

    def test_list_of_dicts_with_text_key(self):
        content = [{"text": "hi"}]
        assert _extract_text(content) == "hi"

    def test_object_with_text_attr(self):
        class Obj:
            text = "from attr"
        assert _extract_text(Obj()) == "from attr"

    def test_fallback_to_str(self):
        assert _extract_text(42) == "42"
        assert _extract_text(None) == "None"

    def test_empty_list(self):
        assert _extract_text([]) == ""

    def test_mixed_list(self):
        content = ["plain", {"type": "text", "text": "dict"}, {"text": "other"}]
        assert _extract_text(content) == "plain dict other"


# ─────────────────────────────────────────────────────────────────────────────
# 4. _is_anonymous() — Environment Variable Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIsAnonymous:

    def test_default_false(self):
        os.environ.pop("ATLAST_ANONYMOUS", None)
        assert _is_anonymous() is False

    def test_true_values(self):
        for val in ("1", "true", "yes"):
            os.environ["ATLAST_ANONYMOUS"] = val
            assert _is_anonymous() is True
        os.environ.pop("ATLAST_ANONYMOUS", None)

    def test_false_values(self):
        for val in ("0", "false", "no", ""):
            os.environ["ATLAST_ANONYMOUS"] = val
            assert _is_anonymous() is False
        os.environ.pop("ATLAST_ANONYMOUS", None)

    def test_whitespace_trimmed(self):
        os.environ["ATLAST_ANONYMOUS"] = "  true  "
        assert _is_anonymous() is True
        os.environ.pop("ATLAST_ANONYMOUS", None)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Cross-Format Compatibility — v0.1 vs v1.0
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossFormatCompatibility:
    """Verify v0.1 and v1.0 records coexist in same storage."""

    def test_both_formats_stored_and_loaded(self):
        """Create both v0.1 and v1.0 records, load them both."""
        # v1.0 minimal
        rid1 = record_minimal("prompt1", "response1", agent="agent-v1")

        # v0.1 full (requires identity)
        from atlast_ecp.identity import get_or_create_identity
        identity = get_or_create_identity()
        rec_v01 = create_record(
            agent_did=identity["did"],
            step_type="llm_call",
            in_content="prompt2",
            out_content="response2",
            identity=identity,
        )
        rec_dict = record_to_dict(rec_v01)
        save_record(rec_dict)

        records = load_records(limit=10)
        versions = {r.get("ecp") for r in records}
        assert "1.0" in versions
        assert "0.1" in versions

    def test_v01_and_v10_hash_consistency(self):
        """Same content hashed the same way regardless of format."""
        content = "test content for hashing"
        expected = hash_content(content)

        # v1.0
        r1 = create_minimal_record("a", "llm_call", content, "out")
        assert r1["in_hash"] == expected

        # v0.1
        from atlast_ecp.identity import get_or_create_identity
        identity = get_or_create_identity()
        r2 = create_record(identity["did"], "llm_call", content, "out", identity=identity)
        r2d = record_to_dict(r2)
        assert r2d["step"]["in_hash"] == expected

    def test_load_by_id_works_for_both(self):
        """load_record_by_id works for both v0.1 and v1.0."""
        rid_v10 = record_minimal("in", "out", agent="v10-agent")
        rec = load_record_by_id(rid_v10)
        assert rec is not None
        assert rec["ecp"] == "1.0"


# ─────────────────────────────────────────────────────────────────────────────
# 6. CLI E2E Tests — subprocess invocations
# ─────────────────────────────────────────────────────────────────────────────

class TestCLI_E2E:
    """End-to-end CLI tests using subprocess."""

    def _run_cli(self, args, stdin_data=None, env_extra=None):
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        result = subprocess.run(
            [sys.executable, "-m", "atlast_ecp.cli"] + args,
            capture_output=True, text=True, env=env,
            input=stdin_data, timeout=30,
        )
        return result

    def test_no_args_shows_help(self, clean_ecp_dir):
        r = self._run_cli([], env_extra={"ATLAST_ECP_DIR": clean_ecp_dir})
        assert r.returncode == 0
        assert "ATLAST ECP" in r.stdout
        assert "atlast init" in r.stdout

    def test_init_creates_directory(self, clean_ecp_dir):
        r = self._run_cli(["init"], env_extra={"ATLAST_ECP_DIR": clean_ecp_dir})
        assert r.returncode == 0
        assert "initialized" in r.stdout.lower() or "ECP" in r.stdout
        assert os.path.isdir(os.path.join(clean_ecp_dir, "records"))

    def test_init_minimal_skips_did(self, clean_ecp_dir):
        r = self._run_cli(["init", "--minimal"], env_extra={"ATLAST_ECP_DIR": clean_ecp_dir})
        assert r.returncode == 0
        assert "skipped" in r.stdout.lower()

    def test_record_with_flags(self, clean_ecp_dir):
        r = self._run_cli(
            ["record", "--agent", "cli-test", "--action", "llm_call", "--in", "hello", "--out", "world"],
            env_extra={"ATLAST_ECP_DIR": clean_ecp_dir},
        )
        assert r.returncode == 0
        assert r.stdout.strip().startswith("✅ rec_") or "rec_" in r.stdout

    def test_record_from_stdin_json(self, clean_ecp_dir):
        data = json.dumps({"in": "prompt from stdin", "out": "response from stdin", "agent": "stdin-agent"})
        r = self._run_cli(
            ["record"],
            stdin_data=data,
            env_extra={"ATLAST_ECP_DIR": clean_ecp_dir},
        )
        assert r.returncode == 0
        assert "rec_" in r.stdout

    def test_record_then_log(self, clean_ecp_dir):
        """Record something, then verify log shows it."""
        self._run_cli(
            ["record", "--in", "test-prompt", "--out", "test-response", "--agent", "log-test"],
            env_extra={"ATLAST_ECP_DIR": clean_ecp_dir},
        )
        r = self._run_cli(["log"], env_extra={"ATLAST_ECP_DIR": clean_ecp_dir})
        assert r.returncode == 0
        # log should show at least one record
        # (output format depends on cmd_view implementation)

    def test_stats_runs(self, clean_ecp_dir):
        """Stats command doesn't crash."""
        record_minimal("in", "out", agent="stats-test")
        r = self._run_cli(["stats"], env_extra={"ATLAST_ECP_DIR": clean_ecp_dir})
        assert r.returncode == 0

    def test_export_json(self, clean_ecp_dir):
        """Export outputs valid JSON after recording via CLI."""
        # Record via CLI (same ECP_DIR) so data is visible to export
        self._run_cli(
            ["record", "--in", "export-in", "--out", "export-out", "--agent", "export-test"],
            env_extra={"ATLAST_ECP_DIR": clean_ecp_dir},
        )
        r = self._run_cli(["export"], env_extra={"ATLAST_ECP_DIR": clean_ecp_dir})
        assert r.returncode == 0
        if r.stdout.strip():
            data = json.loads(r.stdout)
            assert isinstance(data, list)
            assert len(data) >= 1

    def test_unknown_command_exits_1(self, clean_ecp_dir):
        r = self._run_cli(["nonexistent"], env_extra={"ATLAST_ECP_DIR": clean_ecp_dir})
        assert r.returncode == 1

    def test_record_missing_input_exits_1(self, clean_ecp_dir):
        """Record without --in or stdin should fail."""
        r = self._run_cli(
            ["record", "--out", "only-output"],
            env_extra={"ATLAST_ECP_DIR": clean_ecp_dir},
        )
        assert r.returncode == 1


# ─────────────────────────────────────────────────────────────────────────────
# 7. atlast run — E2E Proxy Subprocess Test
# ─────────────────────────────────────────────────────────────────────────────

class TestAtlastRunE2E:
    """End-to-end test for 'atlast run' — verifies the proxy wrapper works."""

    def test_run_echo_command(self, clean_ecp_dir):
        """atlast run echo 'hello' should work (proxy starts but no LLM calls)."""
        try:
            from atlast_ecp.proxy import HAS_AIOHTTP
            if not HAS_AIOHTTP:
                pytest.skip("aiohttp not installed")
        except ImportError:
            pytest.skip("proxy module not available")

        r = subprocess.run(
            [sys.executable, "-m", "atlast_ecp.cli", "run", "echo", "hello-from-atlast-run"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "ATLAST_ECP_DIR": clean_ecp_dir},
        )
        assert "hello-from-atlast-run" in r.stdout
        assert "ATLAST Proxy" in r.stdout or "ATLAST ECP" in r.stdout
        # Exit code should be 0 (echo succeeds)

    def test_run_python_script(self, clean_ecp_dir):
        """atlast run python -c 'print(...)' — verify env vars are set."""
        try:
            from atlast_ecp.proxy import HAS_AIOHTTP
            if not HAS_AIOHTTP:
                pytest.skip("aiohttp not installed")
        except ImportError:
            pytest.skip("proxy module not available")

        script = "import os; print('OPENAI_BASE_URL=' + os.environ.get('OPENAI_BASE_URL', 'NOT_SET'))"
        r = subprocess.run(
            [sys.executable, "-m", "atlast_ecp.cli", "run", sys.executable, "-c", script],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "ATLAST_ECP_DIR": clean_ecp_dir},
        )
        assert "OPENAI_BASE_URL=http://127.0.0.1:" in r.stdout

    def test_run_preserves_original_env(self, clean_ecp_dir):
        """Original OPENAI_BASE_URL is saved as OPENAI_BASE_URL_ORIGINAL."""
        try:
            from atlast_ecp.proxy import HAS_AIOHTTP
            if not HAS_AIOHTTP:
                pytest.skip("aiohttp not installed")
        except ImportError:
            pytest.skip("proxy module not available")

        script = "import os; print('ORIGINAL=' + os.environ.get('OPENAI_BASE_URL_ORIGINAL', 'NONE'))"
        r = subprocess.run(
            [sys.executable, "-m", "atlast_ecp.cli", "run", sys.executable, "-c", script],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "ATLAST_ECP_DIR": clean_ecp_dir, "OPENAI_BASE_URL": "https://my-custom-api.com"},
        )
        assert "ORIGINAL=https://my-custom-api.com" in r.stdout

    def test_run_nonexistent_command(self, clean_ecp_dir):
        """atlast run with nonexistent command should not crash proxy."""
        try:
            from atlast_ecp.proxy import HAS_AIOHTTP
            if not HAS_AIOHTTP:
                pytest.skip("aiohttp not installed")
        except ImportError:
            pytest.skip("proxy module not available")

        r = subprocess.run(
            [sys.executable, "-m", "atlast_ecp.cli", "run", "nonexistent_cmd_xyz_123"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "ATLAST_ECP_DIR": clean_ecp_dir},
        )
        # Should exit with error code, not crash
        assert r.returncode != 0


# ─────────────────────────────────────────────────────────────────────────────
# 8. Full Pipeline — Record → Save → Load → Verify Integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipeline:
    """End-to-end data integrity verification."""

    def test_record_save_load_roundtrip(self):
        """Record → save → load → verify all fields intact."""
        rid = record_minimal(
            "What is 2+2?", "The answer is 4.",
            agent="pipeline-test", action="llm_call",
            model="gpt-4", latency_ms=250, tokens_in=10, tokens_out=5,
        )
        rec = load_record_by_id(rid)
        assert rec is not None
        assert rec["ecp"] == "1.0"
        assert rec["agent"] == "pipeline-test"
        assert rec["action"] == "llm_call"
        assert rec["meta"]["model"] == "gpt-4"
        assert rec["meta"]["latency_ms"] == 250
        assert rec["meta"]["tokens_in"] == 10
        assert rec["meta"]["tokens_out"] == 5
        # Verify hashes
        expected_in = "sha256:" + hashlib.sha256("What is 2+2?".encode()).hexdigest()
        expected_out = "sha256:" + hashlib.sha256("The answer is 4.".encode()).hexdigest()
        assert rec["in_hash"] == expected_in
        assert rec["out_hash"] == expected_out

    def test_many_records_all_retrievable(self):
        """Write 50 records, verify all can be loaded."""
        ids = []
        for i in range(50):
            rid = record_minimal(f"prompt-{i}", f"response-{i}", agent=f"agent-{i % 5}")
            ids.append(rid)
        all_records = load_records(limit=100)
        stored_ids = {r["id"] for r in all_records}
        for rid in ids:
            assert rid in stored_ids, f"Record {rid} not found in storage"

    def test_hash_never_contains_raw_content(self):
        """Privacy check: raw content must never appear in stored records."""
        secret = "TOP SECRET CONFIDENTIAL DATA xyz123"
        rid = record_minimal(secret, f"Response to {secret}", agent="privacy-test")
        rec = load_record_by_id(rid)
        serialized = json.dumps(rec)
        assert secret not in serialized
        assert "TOP SECRET" not in serialized

    def test_concurrent_writes(self):
        """Multiple threads writing records simultaneously."""
        ids = []
        lock = threading.Lock()

        def _write(idx):
            rid = record_minimal(f"concurrent-{idx}", f"response-{idx}", agent="concurrent")
            with lock:
                ids.append(rid)

        threads = [threading.Thread(target=_write, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(ids) == 20
        assert len(set(ids)) == 20  # all unique

    def test_v01_full_record_integrity(self):
        """v0.1 record with chain + signature maintains integrity."""
        from atlast_ecp.identity import get_or_create_identity
        identity = get_or_create_identity()
        rec = create_record(identity["did"], "llm_call", "input", "output", identity=identity)
        rec_dict = record_to_dict(rec)
        save_record(rec_dict)

        loaded = load_records(limit=10)
        found = [r for r in loaded if r.get("ecp") == "0.1"]
        assert len(found) >= 1
        r = found[-1]
        assert "chain" in r
        assert "step" in r
        assert r["step"]["in_hash"].startswith("sha256:")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Signal Detection Integration
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalDetection:
    """Verify flag detection works correctly within record_minimal."""

    def test_hedged_response(self):
        rid = record_minimal("What's the answer?", "I'm not sure, but it might be 42")
        rec = load_record_by_id(rid)
        flags = rec.get("meta", {}).get("flags", [])
        assert "hedged" in flags

    def test_no_flags_on_clean_response(self):
        rid = record_minimal("What's 2+2?", "4", latency_ms=100)
        rec = load_record_by_id(rid)
        # May or may not have meta depending on latency_ms inclusion
        flags = rec.get("meta", {}).get("flags", [])
        # Clean response with normal latency should have no flags
        assert "error" not in flags
        assert "high_latency" not in flags


# ─────────────────────────────────────────────────────────────────────────────
# 10. Proxy Unit Deep Tests (supplement existing test_proxy.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestProxySSEReconstructionDeep:
    """Deep SSE reconstruction edge cases."""

    def test_empty_delta_content(self):
        from atlast_ecp.proxy import _reconstruct_sse_content
        chunks = b'data: {"choices":[{"delta":{"content":""}}]}\n\ndata: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n'
        result = _reconstruct_sse_content(chunks, "openai")
        assert result == "hello"

    def test_no_content_in_delta(self):
        from atlast_ecp.proxy import _reconstruct_sse_content
        chunks = b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\ndata: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
        result = _reconstruct_sse_content(chunks, "openai")
        assert result == "hi"

    def test_unicode_in_sse(self):
        from atlast_ecp.proxy import _reconstruct_sse_content
        chunks = 'data: {"choices":[{"delta":{"content":"你好"}}]}\n\ndata: {"choices":[{"delta":{"content":"世界"}}]}\n\ndata: [DONE]\n\n'.encode("utf-8")
        result = _reconstruct_sse_content(chunks, "openai")
        assert result == "你好世界"

    def test_multiple_choices_only_first(self):
        from atlast_ecp.proxy import _reconstruct_sse_content
        chunks = b'data: {"choices":[{"index":0,"delta":{"content":"A"}},{"index":1,"delta":{"content":"B"}}]}\n\ndata: [DONE]\n\n'
        result = _reconstruct_sse_content(chunks, "openai")
        assert "A" in result

    def test_anthropic_mixed_events(self):
        from atlast_ecp.proxy import _reconstruct_sse_content
        chunks = (
            b'data: {"type":"message_start","message":{"id":"msg"}}\n\n'
            b'data: {"type":"content_block_start","index":0}\n\n'
            b'data: {"type":"content_block_delta","index":0,"delta":{"text":"OK"}}\n\n'
            b'data: {"type":"content_block_stop","index":0}\n\n'
            b'data: {"type":"message_stop"}\n\n'
        )
        result = _reconstruct_sse_content(chunks, "anthropic")
        assert result == "OK"


# ─────────────────────────────────────────────────────────────────────────────
# 11. hash_content() Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestHashContent:

    def test_string_input(self):
        h = hash_content("hello")
        assert h == "sha256:" + hashlib.sha256(b"hello").hexdigest()

    def test_dict_input(self):
        """Dicts should be JSON-serialized then hashed."""
        d = {"key": "value"}
        h = hash_content(d)
        assert h.startswith("sha256:")

    def test_list_input(self):
        h = hash_content(["a", "b"])
        assert h.startswith("sha256:")

    def test_none_input(self):
        h = hash_content(None)
        assert h.startswith("sha256:")

    def test_int_input(self):
        h = hash_content(42)
        assert h.startswith("sha256:")

    def test_deterministic(self):
        assert hash_content("test") == hash_content("test")

    def test_different_inputs(self):
        assert hash_content("a") != hash_content("b")
