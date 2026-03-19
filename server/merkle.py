"""
ECP Reference Server — Merkle Tree Verification

Algorithm matches SDK verify.py build_merkle_root() exactly:
1. Sort hashes lexicographically
2. Pair adjacent hashes, SHA-256 each pair
3. Repeat until one root remains
"""

from __future__ import annotations

import hashlib


def build_merkle_root(hashes: list[str]) -> str:
    """Build Merkle root from a list of hash strings. Matches Python SDK algorithm."""
    if not hashes:
        return ""
    if len(hashes) == 1:
        return hashes[0]

    # Sort lexicographically
    layer = sorted(hashes)

    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            if i + 1 < len(layer):
                combined = layer[i] + layer[i + 1]
            else:
                combined = layer[i] + layer[i]  # duplicate odd element
            h = hashlib.sha256(combined.encode()).hexdigest()
            next_layer.append(f"sha256:{h}")
        layer = next_layer

    return layer[0]


def verify_merkle_root(record_hashes: list[str], claimed_root: str) -> bool:
    """Verify that record hashes produce the claimed Merkle root."""
    if not record_hashes:
        return claimed_root == ""
    computed = build_merkle_root(record_hashes)
    return computed == claimed_root
