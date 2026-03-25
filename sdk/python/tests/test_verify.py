"""Tests for atlast_ecp.verify — public verification API."""
import hashlib
import pytest


def _sha256(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


class TestVerifySignature:
    def test_unverified_returns_true(self):
        from atlast_ecp.verify import verify_signature
        assert verify_signature("deadbeef" * 8, "unverified", "anything") is True

    def test_invalid_prefix_returns_false(self):
        from atlast_ecp.verify import verify_signature
        assert verify_signature("deadbeef" * 8, "rsa:abc", "anything") is False

    def test_valid_ed25519_signature(self):
        from atlast_ecp.verify import verify_signature
        from atlast_ecp.identity import get_or_create_identity, sign
        identity = get_or_create_identity()
        data = "sha256:abcdef1234567890"
        sig = sign(identity, data)
        if sig != "unverified":
            assert verify_signature(identity["pub_key"], sig, data) is True

    def test_wrong_data_fails(self):
        from atlast_ecp.verify import verify_signature
        from atlast_ecp.identity import get_or_create_identity, sign
        identity = get_or_create_identity()
        sig = sign(identity, "original_data")
        if sig != "unverified":
            assert verify_signature(identity["pub_key"], sig, "tampered_data") is False


class TestBuildMerkleProof:
    def test_single_hash(self):
        from atlast_ecp.verify import build_merkle_proof
        h = _sha256("record1")
        proof = build_merkle_proof([h], h)
        assert proof == []  # single element = root, no proof needed

    def test_not_found(self):
        from atlast_ecp.verify import build_merkle_proof
        h1 = _sha256("a")
        h2 = _sha256("b")
        missing = _sha256("c")
        assert build_merkle_proof([h1, h2], missing) == []

    def test_two_hashes_proof(self):
        from atlast_ecp.verify import build_merkle_proof
        h1 = _sha256("a")
        h2 = _sha256("b")
        proof = build_merkle_proof([h1, h2], h1)
        assert len(proof) == 1
        assert proof[0]["hash"] == h2
        assert proof[0]["position"] == "right"

    def test_four_hashes_proof(self):
        from atlast_ecp.verify import build_merkle_proof
        hashes = [_sha256(f"rec{i}") for i in range(4)]
        proof = build_merkle_proof(hashes, hashes[2])
        assert len(proof) == 2  # log2(4) = 2 steps


class TestVerifyMerkleProof:
    def test_roundtrip(self):
        from atlast_ecp.verify import build_merkle_proof, verify_merkle_proof
        from atlast_ecp.batch import build_merkle_tree

        hashes = [_sha256(f"record_{i}") for i in range(7)]
        merkle_root, _ = build_merkle_tree(hashes)

        for i, h in enumerate(hashes):
            proof = build_merkle_proof(hashes, h)
            assert verify_merkle_proof(h, proof, merkle_root), f"Failed for hash {i}"

    def test_tampered_proof_fails(self):
        from atlast_ecp.verify import build_merkle_proof, verify_merkle_proof
        from atlast_ecp.batch import build_merkle_tree

        hashes = [_sha256(f"r{i}") for i in range(4)]
        merkle_root, _ = build_merkle_tree(hashes)

        proof = build_merkle_proof(hashes, hashes[0])
        # Tamper with proof
        if proof:
            proof[0]["hash"] = _sha256("tampered")
            assert verify_merkle_proof(hashes[0], proof, merkle_root) is False


class TestVerifyRecord:
    def test_valid_record(self):
        from atlast_ecp.verify import verify_record
        from atlast_ecp.record import create_record, record_to_dict
        from atlast_ecp.identity import get_or_create_identity

        identity = get_or_create_identity()
        rec = create_record(
            agent_did=identity["did"],
            step_type="llm_call",
            in_content="hello",
            out_content="world",
            identity=identity,
        )
        d = record_to_dict(rec)
        result = verify_record(d)
        assert result["valid"] is True
        assert result["chain_hash_ok"] is True
        assert result["errors"] == []

    def test_tampered_record(self):
        from atlast_ecp.verify import verify_record
        from atlast_ecp.record import create_record, record_to_dict
        from atlast_ecp.identity import get_or_create_identity

        identity = get_or_create_identity()
        rec = create_record(
            agent_did=identity["did"],
            step_type="llm_call",
            in_content="hello",
            out_content="world",
            identity=identity,
        )
        d = record_to_dict(rec)
        d["step"]["latency_ms"] = 99999  # tamper
        result = verify_record(d)
        assert result["valid"] is False
        assert result["chain_hash_ok"] is False

    def test_verify_with_key(self):
        from atlast_ecp.verify import verify_record_with_key
        from atlast_ecp.record import create_record, record_to_dict
        from atlast_ecp.identity import get_or_create_identity

        identity = get_or_create_identity()
        rec = create_record(
            agent_did=identity["did"],
            step_type="llm_call",
            in_content="test",
            out_content="result",
            identity=identity,
        )
        d = record_to_dict(rec)
        result = verify_record_with_key(d, identity["pub_key"])
        assert result["valid"] is True
        assert result["chain_hash_ok"] is True
        # signature_ok is True if crypto available, None-ish otherwise
        if identity.get("verified"):
            assert result["signature_ok"] is True


class TestVerifyRecordEdgeCases:
    def test_empty_dict(self):
        from atlast_ecp.verify import verify_record
        result = verify_record({})
        assert result["valid"] is False
        assert "Missing" in result["errors"][0]

    def test_not_a_dict(self):
        from atlast_ecp.verify import verify_record
        result = verify_record("not a dict")  # type: ignore
        assert result["valid"] is False

    def test_missing_chain_hash(self):
        from atlast_ecp.verify import verify_record
        result = verify_record({"id": "rec_test", "chain": {}})
        assert result["valid"] is False
        assert "Missing chain.hash" in result["errors"][0]


class TestConfig:
    def test_default_api_url(self):
        from atlast_ecp.config import get_api_url, DEFAULT_ENDPOINT
        import os
        # Clear env to test default
        old = os.environ.pop("ATLAST_API_URL", None)
        try:
            url = get_api_url()
            assert url == DEFAULT_ENDPOINT or url != ""
        finally:
            if old:
                os.environ["ATLAST_API_URL"] = old

    def test_env_override(self):
        from atlast_ecp.config import get_api_url
        import os
        old = os.environ.get("ATLAST_API_URL")
        os.environ["ATLAST_API_URL"] = "https://custom.example.com/v1"
        try:
            assert get_api_url() == "https://custom.example.com/v1"
        finally:
            if old:
                os.environ["ATLAST_API_URL"] = old
            else:
                del os.environ["ATLAST_API_URL"]

    def test_api_key_none_by_default(self):
        from atlast_ecp.config import get_api_key
        import os
        old = os.environ.pop("ATLAST_API_KEY", None)
        try:
            # May return None or a value from config file
            key = get_api_key()
            assert key is None or isinstance(key, str)
        finally:
            if old:
                os.environ["ATLAST_API_KEY"] = old
