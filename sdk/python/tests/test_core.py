"""
ECP Core SDK Tests
Tests: identity, record, storage, signals, batch (Merkle)
Run: python -m pytest tests/test_core.py -v
"""

import json
import os
import shutil
import sys
import tempfile
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def temp_ecp_dir(tmp_path, monkeypatch):
    """Each test gets a fresh .ecp/ directory."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    # Reset core state and legacy wrap context
    try:
        from atlast_ecp.core import reset
        reset()
    except Exception:
        pass
    try:
        import sys
        import atlast_ecp.wrap  # ensure loaded
        wrap_mod = sys.modules.get("atlast_ecp.wrap")
        if wrap_mod and hasattr(wrap_mod, "_ctx"):
            wrap_mod._ctx.last_record = None
            wrap_mod._ctx.call_hashes = {}
    except Exception:
        pass


# ─── 1. Identity ──────────────────────────────────────────────────────────────

class TestIdentity:
    def test_creates_did(self):
        from atlast_ecp.identity import get_or_create_identity
        identity = get_or_create_identity()
        assert identity["did"].startswith("did:ecp:")
        # DID identifier must be 32 hex chars (16 bytes)
        did_id = identity["did"].replace("did:ecp:", "")
        assert len(did_id) == 32

    def test_did_is_persistent(self, tmp_path):
        from atlast_ecp.identity import get_or_create_identity
        id1 = get_or_create_identity()
        id2 = get_or_create_identity()
        assert id1["did"] == id2["did"]

    def test_has_keys(self):
        from atlast_ecp.identity import get_or_create_identity
        identity = get_or_create_identity()
        assert "pub_key" in identity
        assert "priv_key" in identity
        assert len(identity["pub_key"]) > 0

    def test_sign_returns_correct_format_or_unverified(self):
        from atlast_ecp.identity import get_or_create_identity, sign
        identity = get_or_create_identity()
        sig = sign(identity, "test payload")
        # Must be either ed25519:hex or "unverified"
        assert sig == "unverified" or sig.startswith("ed25519:")

    def test_sign_with_crypto(self):
        """Test ed25519 signing when cryptography package is available."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            pytest.skip("cryptography not installed")

        from atlast_ecp.identity import _create_identity, sign
        identity = _create_identity()
        assert identity["verified"] is True
        sig = sign(identity, "test payload")
        assert sig.startswith("ed25519:")
        assert len(sig) > 20


# ─── 2. Record ────────────────────────────────────────────────────────────────

class TestRecord:
    def setup_method(self):
        from atlast_ecp.identity import get_or_create_identity
        self.identity = get_or_create_identity()
        self.did = self.identity["did"]

    def test_record_id_prefix(self):
        from atlast_ecp.record import create_record
        r = create_record(self.did, "llm_call", "input", "output", self.identity)
        assert r.id.startswith("rec_"), f"ID should start with rec_, got: {r.id}"

    def test_record_agent_did(self):
        from atlast_ecp.record import create_record
        r = create_record(self.did, "llm_call", "input", "output", self.identity)
        assert r.agent == self.did

    def test_hash_format(self):
        from atlast_ecp.record import create_record
        r = create_record(self.did, "llm_call", "input", "output", self.identity)
        assert r.step.in_hash.startswith("sha256:"), f"in_hash must start with sha256:, got: {r.step.in_hash}"
        assert r.step.out_hash.startswith("sha256:"), f"out_hash must start with sha256:, got: {r.step.out_hash}"

    def test_genesis_chain_prev(self):
        from atlast_ecp.record import create_record
        r = create_record(self.did, "llm_call", "input", "output", self.identity, prev_record=None)
        assert r.chain.prev == "genesis", f"First record chain.prev must be 'genesis', got: {r.chain.prev}"

    def test_chain_link(self):
        from atlast_ecp.record import create_record
        r1 = create_record(self.did, "llm_call", "input1", "output1", self.identity)
        r2 = create_record(self.did, "llm_call", "input2", "output2", self.identity, prev_record=r1)
        assert r2.chain.prev == r1.id

    def test_chain_hash_format(self):
        from atlast_ecp.record import create_record
        r = create_record(self.did, "llm_call", "input", "output", self.identity)
        assert r.chain.hash.startswith("sha256:"), f"chain.hash must start with sha256:, got: {r.chain.hash}"

    def test_record_to_dict_has_ecp_version(self):
        from atlast_ecp.record import create_record, record_to_dict
        r = create_record(self.did, "llm_call", "input", "output", self.identity)
        d = record_to_dict(r)
        assert d.get("ecp") == "0.1", f"Record must have ecp='0.1', got: {d.get('ecp')}"

    def test_record_types(self):
        from atlast_ecp.record import create_record
        for step_type in ["llm_call", "tool_call", "turn", "a2a_call"]:
            r = create_record(self.did, step_type, "input", "output", self.identity)
            assert r.step.type == step_type

    def test_deterministic_hash(self):
        """Same content must produce same hash."""
        from atlast_ecp.record import hash_content
        h1 = hash_content("hello world")
        h2 = hash_content("hello world")
        assert h1 == h2

    def test_different_content_different_hash(self):
        from atlast_ecp.record import hash_content
        h1 = hash_content("hello world")
        h2 = hash_content("hello world!")
        assert h1 != h2

    def test_chain_hash_tamper_detection(self):
        """Modifying a record should change chain.hash."""
        from atlast_ecp.record import create_record, record_to_dict, compute_chain_hash
        r = create_record(self.did, "llm_call", "input", "output", self.identity)
        d = record_to_dict(r)
        original_hash = d["chain"]["hash"]

        # Tamper with the record
        d["step"]["out_hash"] = "sha256:tampered000000"
        new_hash = compute_chain_hash(d)

        assert original_hash != new_hash, "Tampered record must produce different chain hash"

    def test_no_confidence_field(self):
        """ECP-SPEC: confidence field must NOT exist."""
        from atlast_ecp.record import create_record, record_to_dict
        r = create_record(self.did, "llm_call", "input", "output", self.identity)
        d = record_to_dict(r)
        assert "confidence" not in d
        assert "confidence" not in d.get("step", {})


# ─── 3. Signals ───────────────────────────────────────────────────────────────

class TestSignals:
    def test_hedge_detection(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("I think this might be correct, but I'm not sure.")
        assert "hedged" in flags

    def test_hedge_chinese(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("我觉得这个答案可能是对的，但不确定。")
        assert "hedged" in flags

    def test_no_false_hedge(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("The contract expires on March 31, 2026.")
        assert "hedged" not in flags

    def test_incomplete_detection(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("I cannot access that file directly.")
        assert "incomplete" in flags

    def test_error_detection(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("Traceback (most recent call last):\n  ValueError: invalid input")
        assert "error" in flags

    def test_human_review_detection(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("Please consult a lawyer before signing this contract.")
        assert "human_review" in flags

    def test_retry_flag(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("The answer is 42.", is_retry=True)
        assert "retried" in flags

    def test_high_latency_detection(self):
        from atlast_ecp.signals import detect_flags
        # absolute threshold: > 5000ms
        flags_high = detect_flags("answer", latency_ms=6000)
        flags_normal = detect_flags("answer", latency_ms=500)
        assert "high_latency" in flags_high
        assert "high_latency" not in flags_normal

    def test_high_latency_2x_median(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("answer", latency_ms=3000, median_latency_ms=1000)
        assert "high_latency" in flags  # 3000 > 2*1000

    def test_empty_output_is_incomplete(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("")
        assert "incomplete" in flags

    def test_flags_sorted(self):
        from atlast_ecp.signals import detect_flags
        flags = detect_flags("I think this is correct", is_retry=True)
        assert flags == sorted(flags)

    def test_all_spec_flags_exist(self):
        """All 7 flags from ECP-SPEC §4 must be detectable."""
        from atlast_ecp.signals import detect_flags
        # retried
        assert "retried" in detect_flags("ok", is_retry=True)
        # hedged
        assert "hedged" in detect_flags("I think maybe")
        # incomplete
        assert "incomplete" in detect_flags("I cannot do that")
        # high_latency
        assert "high_latency" in detect_flags("ok", latency_ms=9999)
        # error
        assert "error" in detect_flags("Traceback (most recent call last):")
        # human_review
        assert "human_review" in detect_flags("Please consult a lawyer")
        # a2a_delegated
        assert "a2a_delegated" in detect_flags("ok", is_a2a=True)


# ─── 4. Storage ───────────────────────────────────────────────────────────────

class TestStorage:
    def test_save_and_load(self):
        from atlast_ecp.identity import get_or_create_identity
        from atlast_ecp.record import create_record, record_to_dict
        from atlast_ecp.storage import save_record, load_records, load_record_by_id

        identity = get_or_create_identity()
        r = create_record(identity["did"], "llm_call", "input", "output", identity)
        d = record_to_dict(r)
        save_record(d)

        records = load_records(limit=10)
        assert len(records) == 1
        assert records[0]["id"] == r.id

    def test_load_by_id(self):
        from atlast_ecp.identity import get_or_create_identity
        from atlast_ecp.record import create_record, record_to_dict
        from atlast_ecp.storage import save_record, load_record_by_id

        identity = get_or_create_identity()
        r = create_record(identity["did"], "llm_call", "input", "output", identity)
        d = record_to_dict(r)
        save_record(d)

        loaded = load_record_by_id(r.id)
        assert loaded is not None
        assert loaded["id"] == r.id

    def test_load_nonexistent_returns_none(self):
        from atlast_ecp.storage import load_record_by_id
        result = load_record_by_id("rec_nonexistent123")
        assert result is None

    def test_local_summary_not_in_record(self):
        """Summary must never be included in the transmitted record."""
        from atlast_ecp.identity import get_or_create_identity
        from atlast_ecp.record import create_record, record_to_dict
        from atlast_ecp.storage import save_record, load_records, load_local_summary

        identity = get_or_create_identity()
        r = create_record(identity["did"], "llm_call", "input", "output", identity)
        d = record_to_dict(r)
        save_record(d, local_summary="This is a private summary — NEVER upload")

        records = load_records(limit=1)
        assert "summary" not in records[0]
        assert "summary" not in records[0].get("step", {})

        summary = load_local_summary(r.id)
        assert summary == "This is a private summary — NEVER upload"


# ─── 5. Merkle Tree ───────────────────────────────────────────────────────────

class TestMerkle:
    def test_merkle_root_deterministic(self):
        from atlast_ecp.batch import build_merkle_tree
        hashes = ["a", "b", "c", "d"]
        root1, _ = build_merkle_tree(hashes)
        root2, _ = build_merkle_tree(hashes)
        assert root1 == root2

    def test_merkle_root_changes_on_tamper(self):
        from atlast_ecp.batch import build_merkle_tree
        hashes = ["a", "b", "c", "d"]
        root1, _ = build_merkle_tree(hashes)
        hashes_tampered = ["a", "b", "c", "X"]
        root2, _ = build_merkle_tree(hashes_tampered)
        assert root1 != root2

    def test_merkle_single_element(self):
        from atlast_ecp.batch import build_merkle_tree
        root, layers = build_merkle_tree(["only_one"])
        assert root == "only_one"

    def test_merkle_proof_generated(self):
        from atlast_ecp.batch import build_merkle_tree, get_merkle_proof
        hashes = ["h0", "h1", "h2", "h3"]
        root, _ = build_merkle_tree(hashes)
        proof = get_merkle_proof(hashes, 0)
        assert len(proof) > 0
        for step in proof:
            assert "hash" in step
            assert "position" in step

    def test_merkle_odd_number_of_leaves(self):
        from atlast_ecp.batch import build_merkle_tree
        # Odd count: last element duplicated
        hashes = ["a", "b", "c"]
        root, _ = build_merkle_tree(hashes)
        assert root  # Should not crash

    def test_empty_merkle(self):
        from atlast_ecp.batch import build_merkle_tree
        root, _ = build_merkle_tree([])
        assert root  # Returns sha256("empty")
        assert root.startswith("sha256:")  # Must have prefix

    def test_merkle_root_has_sha256_prefix(self):
        """Root must have sha256: prefix — backend validator requires it."""
        from atlast_ecp.batch import build_merkle_tree
        hashes = ["sha256:aaa", "sha256:bbb", "sha256:ccc", "sha256:ddd"]
        root, _ = build_merkle_tree(hashes)
        assert root.startswith("sha256:"), f"Root must start with sha256:, got: {root}"

    def test_merkle_intermediate_nodes_have_prefix(self):
        """All tree levels must have sha256: prefix (not just leaves)."""
        from atlast_ecp.batch import build_merkle_tree
        hashes = ["sha256:a1", "sha256:b2", "sha256:c3", "sha256:d4"]
        root, layers = build_merkle_tree(hashes)
        for layer in layers[1:]:  # Skip leaves (provided by caller)
            for node in layer:
                assert node.startswith("sha256:"), f"Node must have sha256: prefix: {node}"

    def test_batch_record_hashes_payload(self):
        """_build_record_hashes_payload returns valid entries for backend."""
        from atlast_ecp.batch import _build_record_hashes_payload
        records = [
            {"id": "rec_abc123", "chain": {"hash": "sha256:deadbeef"}, "step": {"flags": {"hedged": True, "retried": False}}},
            {"id": "rec_def456", "chain": {"hash": "sha256:cafebabe"}, "step": {"flags": {}}},
            {"id": "bad_id", "chain": {"hash": "sha256:xxx"}},           # bad ID — should be excluded
            {"id": "rec_ok789", "chain": {"hash": "nohash"}},            # bad hash — should be excluded
        ]
        result = _build_record_hashes_payload(records)
        assert len(result) == 2  # Only valid entries
        assert all(e["id"].startswith("rec_") for e in result)
        assert all(e["hash"].startswith("sha256:") for e in result)
        assert "flags" in result[0]

    def test_aggregate_flag_counts(self):
        """_aggregate_flag_counts aggregates correctly with list-style flags."""
        from atlast_ecp.batch import _aggregate_flag_counts
        records = [
            {"step": {"flags": ["hedged", "retried"]}},
            {"step": {"flags": ["hedged"]}},
            {"step": {"flags": ["error"]}},
            {"step": {}},  # No flags key
        ]
        counts = _aggregate_flag_counts(records)
        assert counts["hedged"] == 2
        assert counts["retried"] == 1
        assert counts["error"] == 1
        assert "confidence" not in counts  # No confidence field

    def test_upload_payload_has_batch_ts_as_int(self):
        """upload_merkle_root must send batch_ts as int (Unix ms), not ISO string."""
        import json
        import unittest.mock as mock
        from atlast_ecp.batch import upload_merkle_root

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            raise Exception("abort_after_capture")  # Don't actually send

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            upload_merkle_root(
                merkle_root="sha256:abc123",
                agent_did="did:ecp:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                record_count=5,
                avg_latency_ms=100,
                batch_ts=1710000000000,  # Unix ms
                sig="unverified",
            )

        body = captured.get("body", {})
        assert isinstance(body.get("batch_ts"), int), "batch_ts must be int, not string"
        assert "sig" in body, "sig field must be present in payload"
        assert body["sig"] == "unverified"
        assert body["merkle_root"].startswith("sha256:")


# ─── 6. Chain Integrity ───────────────────────────────────────────────────────

class TestChainIntegrity:
    def test_valid_chain(self):
        from atlast_ecp.identity import get_or_create_identity
        from atlast_ecp.record import create_record, record_to_dict
        from atlast_ecp.signals import _check_chain_integrity

        identity = get_or_create_identity()
        r1 = create_record(identity["did"], "llm_call", "a", "b", identity)
        r2 = create_record(identity["did"], "llm_call", "c", "d", identity, prev_record=r1)
        r3 = create_record(identity["did"], "llm_call", "e", "f", identity, prev_record=r2)

        records = [record_to_dict(r1), record_to_dict(r2), record_to_dict(r3)]
        assert _check_chain_integrity(records) is True

    def test_broken_chain_detected(self):
        from atlast_ecp.identity import get_or_create_identity
        from atlast_ecp.record import create_record, record_to_dict
        from atlast_ecp.signals import _check_chain_integrity

        identity = get_or_create_identity()
        r1 = create_record(identity["did"], "llm_call", "a", "b", identity)
        r2 = create_record(identity["did"], "llm_call", "c", "d", identity, prev_record=r1)

        d1 = record_to_dict(r1)
        d2 = record_to_dict(r2)
        d2["chain"]["prev"] = "rec_tampered_id_000"  # Break the chain

        assert _check_chain_integrity([d1, d2]) is False


# ─── 7. Core Unified Interface ────────────────────────────────────────────────

class TestCore:
    def test_core_record_returns_id(self):
        from atlast_ecp.core import record, reset
        reset()
        rid = record("hello", "world")
        assert rid is not None
        assert rid.startswith("rec_")

    def test_core_record_creates_file(self):
        from atlast_ecp.core import record, reset
        from atlast_ecp.storage import load_records
        reset()
        record("input1", "output1")
        records = load_records(limit=10)
        assert len(records) >= 1

    def test_core_record_chains(self):
        from atlast_ecp.core import record, reset
        from atlast_ecp.storage import load_records
        reset()
        record("a", "b")
        record("c", "d")
        records = load_records(limit=10)
        # newest first
        assert records[0]["chain"]["prev"] != "genesis"

    def test_core_record_genesis_first(self):
        from atlast_ecp.core import record, reset
        from atlast_ecp.storage import load_records
        reset()
        record("first", "record")
        records = load_records(limit=1)
        assert records[0]["chain"]["prev"] == "genesis"

    def test_core_record_detects_hedge(self):
        import time
        from atlast_ecp.core import record, reset
        from atlast_ecp.storage import load_records
        reset()
        record("question", "I think maybe this is correct, but I'm not sure")
        time.sleep(0.1)
        records = load_records(limit=1)
        assert "hedged" in records[0]["step"]["flags"]

    def test_core_record_fail_open(self):
        from atlast_ecp.core import record, reset
        reset()
        # Even with bad input types, should return None not raise
        result = record(None, None)
        # Should not raise — Fail-Open

    def test_core_record_async_does_not_block(self):
        import time
        from atlast_ecp.core import record_async, reset
        reset()
        start = time.time()
        record_async("input", "output")
        elapsed = time.time() - start
        assert elapsed < 0.1  # Should be near-instant

    def test_core_get_identity(self):
        from atlast_ecp.core import get_identity
        identity = get_identity()
        assert identity["did"].startswith("did:ecp:")

    def test_core_reset(self):
        from atlast_ecp.core import record, reset
        from atlast_ecp.storage import load_records
        reset()
        record("a", "b")
        reset()
        record("c", "d")
        records = load_records(limit=10)
        # After reset, the second record should be genesis
        # Find the record with input hash of "c"/"d"
        # Since reset clears last_record, the new record should have prev=genesis
        genesis_records = [r for r in records if r["chain"]["prev"] == "genesis"]
        assert len(genesis_records) >= 2
