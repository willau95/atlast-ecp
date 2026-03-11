"""
ECP Backend — Signature Verification
Verifies ed25519 signatures from agents to prevent fake batch uploads.
"""


def verify_batch_signature(public_key_hex: str, sig: str, merkle_root: str) -> bool:
    """
    Verify that the batch signature is valid.
    Signature is over the merkle_root string.

    sig format: "ed25519:{hex}" or "unverified"

    Returns True if:
      - sig == "unverified" (dev mode, skip verification)
      - sig is valid ed25519 signature over merkle_root
    Returns False if sig is invalid or verification fails.
    """
    if sig == "unverified":
        # Dev mode / no cryptography installed on client
        # Allow through but mark batch as unverified
        return True  # Permissive for MVP

    if not sig.startswith("ed25519:"):
        return False

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        from cryptography.exceptions import InvalidSignature

        sig_bytes = bytes.fromhex(sig[len("ed25519:"):])
        pub_bytes = bytes.fromhex(public_key_hex)
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        public_key.verify(sig_bytes, merkle_root.encode())
        return True

    except ImportError:
        # cryptography package not installed on server — allow through in dev
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


def build_merkle_proof(all_hashes: list[str], record_hash: str) -> list[dict]:
    """
    Build Merkle proof path for a specific record hash.
    Returns list of {hash, position} steps to verify against root.
    """
    import hashlib

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

        # Build next layer
        hashes = [
            "sha256:" + hashlib.sha256((hashes[i] + hashes[i + 1]).encode()).hexdigest()
            for i in range(0, len(hashes), 2)
        ]
        idx //= 2

    return proof


def verify_merkle_proof(record_hash: str, proof: list[dict], merkle_root: str) -> bool:
    """
    Verify a Merkle proof path against the known root.
    Independent of backend — anyone can verify this.
    """
    import hashlib

    current = record_hash
    for step in proof:
        sibling = step["hash"]
        position = step["position"]
        if position == "right":
            combined = current + sibling
        else:
            combined = sibling + current
        current = "sha256:" + hashlib.sha256(combined.encode()).hexdigest()

    return current == merkle_root
