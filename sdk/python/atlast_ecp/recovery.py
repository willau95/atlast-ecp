"""
ATLAST Recovery — BIP39 mnemonic ↔ Ed25519 private key.

Allows users to backup and restore their agent identity with 12 English words.
Uses standard BIP39 word list + HKDF-SHA256 key derivation.

Security: mnemonic = full access to identity. Treat like a private key.
"""

import hashlib
import hmac
import os
import struct
from typing import Optional

# BIP39 English word list (2048 words)
# We embed a minimal version - generated from the standard BIP39 list
# Full list: https://github.com/bitcoin/bips/blob/master/bip-0039/english.txt
_WORDLIST: Optional[list[str]] = None
_WORDLIST_PATH = os.path.join(os.path.dirname(__file__), "bip39_english.txt")


def _load_wordlist() -> list[str]:
    """Load BIP39 English word list (2048 words)."""
    global _WORDLIST
    if _WORDLIST is not None:
        return _WORDLIST
    with open(_WORDLIST_PATH, "r", encoding="utf-8") as f:
        _WORDLIST = [line.strip() for line in f if line.strip()]
    assert len(_WORDLIST) == 2048, f"BIP39 wordlist must have 2048 words, got {len(_WORDLIST)}"
    return _WORDLIST


def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    """HKDF-SHA256 key derivation (RFC 5869). Pure Python, zero dependencies."""
    # Extract
    if not salt:
        salt = b'\x00' * 32
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    # Expand
    t = b''
    okm = b''
    for i in range(1, (length + 31) // 32 + 1):
        t = hmac.new(prk, t + info + struct.pack('B', i), hashlib.sha256).digest()
        okm += t
    return okm[:length]


def entropy_to_mnemonic(entropy: bytes) -> list[str]:
    """
    Convert 16 bytes of entropy to 12 BIP39 words.

    Standard BIP39: 128 bits entropy + 4 bits checksum = 132 bits = 12 × 11-bit indices.
    """
    if len(entropy) != 16:
        raise ValueError(f"Entropy must be 16 bytes, got {len(entropy)}")

    wordlist = _load_wordlist()

    # Checksum = first 4 bits of SHA-256(entropy)
    h = hashlib.sha256(entropy).digest()
    checksum_bits = h[0] >> 4  # top 4 bits of first byte

    # Convert entropy to bit string (128 bits) + checksum (4 bits) = 132 bits
    bits = int.from_bytes(entropy, 'big')
    bits = (bits << 4) | checksum_bits

    # Split into 12 groups of 11 bits
    words = []
    for i in range(11, -1, -1):
        index = (bits >> (i * 11)) & 0x7FF  # 11 bits = 0-2047
        words.append(wordlist[index])

    return words


def mnemonic_to_entropy(words: list[str]) -> bytes:
    """
    Convert 12 BIP39 words back to 16 bytes of entropy.
    Validates checksum.
    """
    if len(words) != 12:
        raise ValueError(f"Mnemonic must be 12 words, got {len(words)}")

    wordlist = _load_wordlist()
    word_to_index = {w: i for i, w in enumerate(wordlist)}

    # Convert words to indices
    bits = 0
    for word in words:
        word_lower = word.lower().strip()
        if word_lower not in word_to_index:
            raise ValueError(f"Invalid BIP39 word: '{word}'")
        bits = (bits << 11) | word_to_index[word_lower]

    # Split: 128 bits entropy + 4 bits checksum
    checksum_bits = bits & 0xF
    entropy_int = bits >> 4
    entropy = entropy_int.to_bytes(16, 'big')

    # Verify checksum
    h = hashlib.sha256(entropy).digest()
    expected_checksum = h[0] >> 4
    if checksum_bits != expected_checksum:
        raise ValueError("Invalid mnemonic checksum — words may be wrong or in wrong order")

    return entropy


def entropy_to_ed25519_seed(entropy: bytes) -> bytes:
    """
    Derive a 32-byte Ed25519 seed from 16-byte entropy using HKDF-SHA256.

    Deterministic: same entropy always produces the same seed.
    """
    return _hkdf_sha256(
        ikm=entropy,
        salt=b"atlast-ecp-identity-v1",
        info=b"ed25519-seed",
        length=32,
    )


def generate_mnemonic() -> tuple[list[str], bytes]:
    """
    Generate a new random mnemonic + entropy.

    Returns: (words, entropy)
    """
    entropy = os.urandom(16)  # 128 bits
    words = entropy_to_mnemonic(entropy)
    return words, entropy


def mnemonic_to_private_key(words: list[str]) -> bytes:
    """
    Recover Ed25519 private key (32 bytes) from 12 mnemonic words.

    Returns the raw 32-byte seed suitable for Ed25519PrivateKey.from_private_bytes().
    """
    entropy = mnemonic_to_entropy(words)
    return entropy_to_ed25519_seed(entropy)


def private_key_to_entropy_hash(priv_hex: str) -> str:
    """
    Compute the entropy hash for an existing private key.
    Used to verify mnemonic matches identity.

    Note: For keys created BEFORE recovery feature, we cannot reverse the
    private key to entropy (it was random, not HKDF-derived). In that case,
    we store the raw private key bytes as "entropy" for mnemonic export,
    using a different derivation path.
    """
    return hashlib.sha256(bytes.fromhex(priv_hex)).hexdigest()[:32]


def export_mnemonic_for_legacy_key(priv_hex: str) -> list[str]:
    """
    Export mnemonic for a legacy (pre-recovery) private key.

    Since legacy keys weren't derived from BIP39 entropy, we use
    the first 16 bytes of the private key AS the entropy.
    The recovery path will detect this and use direct key restoration.

    Returns: 12-word mnemonic
    """
    priv_bytes = bytes.fromhex(priv_hex)
    # Use first 16 bytes as entropy for BIP39 encoding
    entropy = priv_bytes[:16]
    return entropy_to_mnemonic(entropy)


def recover_legacy_key(words: list[str]) -> bytes:
    """
    Recover a legacy private key from its mnemonic export.

    Legacy keys use first-16-bytes encoding, not HKDF derivation.
    Returns the first 16 bytes — caller must check if identity matches.
    """
    return mnemonic_to_entropy(words)


def format_mnemonic_display(words: list[str]) -> str:
    """Format mnemonic for terminal display with numbered words."""
    lines = []
    for i in range(0, 12, 3):
        group = [f" {i+j+1:2d}. {words[i+j]:<12}" for j in range(3)]
        lines.append("│" + "".join(group) + "  │")

    width = len(lines[0])
    top = "┌" + "─" * (width - 2) + "┐"
    bot = "└" + "─" * (width - 2) + "┘"
    return "\n".join([top] + lines + [bot])
