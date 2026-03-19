"""
ECP Verification — Public API for verifying ECP records, signatures, and Merkle proofs.

These functions are designed to be used by:
1. atlast-ecp SDK users verifying records locally
2. Any ECP-compatible backend (import atlast_ecp and call these directly)
3. Any third-party verifier

Usage:
    from atlast_ecp import verify_signature, verify_merkle_proof, build_merkle_proof

    # Verify a batch signature
    ok = verify_signature(public_key_hex, signature, merkle_root)

    # Build Merkle proof for a specific record
    proof = build_merkle_proof(all_hashes, target_hash)

    # Verify a Merkle proof
    valid = verify_merkle_proof(record_hash, proof, merkle_root)

    # Verify a full ECP record (chain hash integrity)
    valid = verify_record(record_dict)
"""

import hashlib
from typing import Optional


# ─── Signature Verification ───────────────────────────────────────────────────

def verify_signature(public_key_hex: str, sig: str, data: str) -> bool:
    """
    Verify an Ed25519 signature against data.

    Args:
        public_key_hex: 64-char hex string of the Ed25519 public key
        sig: Signature in format "ed25519:{hex}" or "unverified"
        data: The original data that was signed (e.g., merkle_root string)

    Returns:
        True if signature is valid, False if invalid.
        "unverified" signatures return True (agent without cryptography package).
    """
    if sig == "unverified":
        return True

    if not sig.startswith("ed25519:"):
        return False

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature

        sig_bytes = bytes.fromhex(sig[len("ed25519:"):])
        pub_bytes = bytes.fromhex(public_key_hex)
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        public_key.verify(sig_bytes, data.encode())
        return True
    except ImportError:
        # No cryptography package — cannot verify, assume valid
        return True
    except Exception:
        return False


# ─── Merkle Proof ─────────────────────────────────────────────────────────────

def _sha256(data: str) -> str:
    """SHA-256 with sha256: prefix — matches ECP-SPEC and batch.py."""
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def build_merkle_proof(all_hashes: list[str], record_hash: str) -> list[dict]:
    """
    Build a Merkle proof path for a specific record hash.

    Args:
        all_hashes: All record hashes (sha256: prefixed) in the batch, in order
        record_hash: The specific record's hash to prove inclusion of

    Returns:
        List of {hash, position} steps for verification.
        Empty list if record_hash not found in all_hashes.
    """
    if record_hash not in all_hashes:
        return []

    hashes = list(all_hashes)
    idx = hashes.index(record_hash)
    proof = []

    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes = hashes + [hashes[-1]]

        sibling_idx = idx ^ 1
        position = "right" if idx % 2 == 0 else "left"
        proof.append({"hash": hashes[sibling_idx], "position": position})

        hashes = [
            _sha256(hashes[i] + hashes[i + 1])
            for i in range(0, len(hashes), 2)
        ]
        idx //= 2

    return proof


def verify_merkle_proof(record_hash: str, proof: list[dict], merkle_root: str) -> bool:
    """
    Verify a Merkle proof for a record against a known Merkle root.

    Args:
        record_hash: The record's hash (sha256: prefixed)
        proof: Proof path from build_merkle_proof()
        merkle_root: The batch's Merkle root (sha256: prefixed)

    Returns:
        True if the proof is valid (record is included in the batch).
    """
    current = record_hash
    for step in proof:
        sibling = step["hash"]
        position = step["position"]
        if position == "right":
            combined = current + sibling
        else:
            combined = sibling + current
        current = _sha256(combined)

    return current == merkle_root


# ─── Record Verification ─────────────────────────────────────────────────────

def verify_record(record_dict: dict) -> dict:
    """
    Verify a full ECP record's integrity.

    Checks:
    1. Chain hash matches recomputed hash
    2. Signature is valid (if public_key available)

    Args:
        record_dict: Full ECP record as dict

    Returns:
        Dict with verification results:
        {
            "valid": bool,
            "chain_hash_ok": bool,
            "signature_ok": bool | None,  # None if no public_key provided
            "errors": [str]
        }
    """
    from .record import compute_chain_hash

    errors = []

    # 0. Required field check
    if not isinstance(record_dict, dict):
        return {"valid": False, "chain_hash_ok": False, "signature_ok": None, "errors": ["Input is not a dict"]}
    if "chain" not in record_dict or "hash" not in record_dict.get("chain", {}):
        return {"valid": False, "chain_hash_ok": False, "signature_ok": None, "errors": ["Missing chain.hash field"]}
    if "id" not in record_dict:
        return {"valid": False, "chain_hash_ok": False, "signature_ok": None, "errors": ["Missing id field"]}

    # 1. Chain hash integrity
    expected_hash = compute_chain_hash(record_dict)
    actual_hash = record_dict.get("chain", {}).get("hash", "")
    chain_hash_ok = expected_hash == actual_hash
    if not chain_hash_ok:
        errors.append(f"Chain hash mismatch: expected {expected_hash[:20]}..., got {actual_hash[:20]}...")

    # 2. Signature verification
    sig = record_dict.get("sig", "unverified")
    signature_ok = None  # unknown unless we have pubkey

    if sig == "unverified":
        signature_ok = None  # Cannot verify — no signature present
    elif sig.startswith("ed25519:"):
        # Try to load local identity to verify
        try:
            from .identity import get_or_create_identity
            identity = get_or_create_identity()
            agent_did = record_dict.get("agent", "")
            local_did = identity.get("did", "")
            pub_key = identity.get("crypto_pub_key") or identity.get("pub_key")
            if agent_did == local_did and pub_key:
                signature_ok = verify_signature(pub_key, sig, actual_hash)
                if not signature_ok:
                    errors.append("Signature verification failed against local identity")
        except Exception:
            pass  # Can't load identity — leave as None

    return {
        "valid": chain_hash_ok and (signature_ok is not False),
        "chain_hash_ok": chain_hash_ok,
        "signature_ok": signature_ok,
        "errors": errors,
    }


def verify_record_with_key(record_dict: dict, public_key_hex: str) -> dict:
    """
    Verify a full ECP record including signature verification.

    Args:
        record_dict: Full ECP record as dict
        public_key_hex: Agent's Ed25519 public key (64 hex chars)

    Returns:
        Same as verify_record() but with signature_ok filled in.
    """
    result = verify_record(record_dict)

    sig = record_dict.get("sig", "unverified")
    chain_hash = record_dict.get("chain", {}).get("hash", "")

    sig_ok = verify_signature(public_key_hex, sig, chain_hash)
    result["signature_ok"] = sig_ok

    if not sig_ok:
        result["errors"].append("Signature verification failed")
        result["valid"] = False

    return result
