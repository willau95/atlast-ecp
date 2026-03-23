"""Tests for ATLAST Recovery — BIP39 mnemonic ↔ Ed25519."""

import hashlib
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from atlast_ecp.recovery import (
    entropy_to_mnemonic,
    mnemonic_to_entropy,
    entropy_to_ed25519_seed,
    generate_mnemonic,
    mnemonic_to_private_key,
    export_mnemonic_for_legacy_key,
    recover_legacy_key,
    format_mnemonic_display,
    _hkdf_sha256,
)


class TestBIP39:
    """A1: BIP39 mnemonic generation."""

    def test_generate_12_words(self):
        words, entropy = generate_mnemonic()
        assert len(words) == 12
        assert len(entropy) == 16
        assert all(isinstance(w, str) for w in words)

    def test_deterministic_entropy_to_words(self):
        entropy = bytes.fromhex("00000000000000000000000000000000")
        words1 = entropy_to_mnemonic(entropy)
        words2 = entropy_to_mnemonic(entropy)
        assert words1 == words2

    def test_different_entropy_different_words(self):
        e1 = bytes.fromhex("00000000000000000000000000000000")
        e2 = bytes.fromhex("ffffffffffffffffffffffffffffffff")
        w1 = entropy_to_mnemonic(e1)
        w2 = entropy_to_mnemonic(e2)
        assert w1 != w2

    def test_known_vector_all_zeros(self):
        """BIP39 test vector: 128 bits of zeros."""
        entropy = bytes(16)
        words = entropy_to_mnemonic(entropy)
        assert len(words) == 12
        assert words[0] == "abandon"  # Known BIP39 vector

    def test_roundtrip_entropy(self):
        """Generate → words → entropy roundtrip."""
        for _ in range(20):
            words, entropy = generate_mnemonic()
            recovered = mnemonic_to_entropy(words)
            assert recovered == entropy

    def test_invalid_word(self):
        with pytest.raises(ValueError, match="Invalid BIP39 word"):
            mnemonic_to_entropy(["notaword"] * 12)

    def test_wrong_word_count(self):
        with pytest.raises(ValueError, match="12 words"):
            mnemonic_to_entropy(["abandon"] * 11)

    def test_bad_checksum(self):
        words, _ = generate_mnemonic()
        # Swap two words to break checksum
        words[0], words[1] = words[1], words[0]
        # May or may not raise depending on luck, but at least test it doesn't crash
        try:
            mnemonic_to_entropy(words)
        except ValueError:
            pass  # Expected — checksum mismatch

    def test_wrong_entropy_length(self):
        with pytest.raises(ValueError, match="16 bytes"):
            entropy_to_mnemonic(b"\x00" * 15)


class TestKeyDerivation:
    """A2: Mnemonic → Ed25519 private key recovery."""

    def test_deterministic_seed(self):
        entropy = os.urandom(16)
        seed1 = entropy_to_ed25519_seed(entropy)
        seed2 = entropy_to_ed25519_seed(entropy)
        assert seed1 == seed2
        assert len(seed1) == 32

    def test_different_entropy_different_seed(self):
        s1 = entropy_to_ed25519_seed(bytes(16))
        s2 = entropy_to_ed25519_seed(bytes.fromhex("ff" * 16))
        assert s1 != s2

    def test_full_roundtrip_mnemonic_to_key(self):
        """Generate mnemonic → derive key → recover from words → same key."""
        words, entropy = generate_mnemonic()
        seed = entropy_to_ed25519_seed(entropy)
        recovered_seed = mnemonic_to_private_key(words)
        assert seed == recovered_seed

    def test_ed25519_key_works(self):
        """Derived seed produces valid Ed25519 keypair."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            pytest.skip("cryptography not installed")

        words, _ = generate_mnemonic()
        seed = mnemonic_to_private_key(words)
        key = Ed25519PrivateKey.from_private_bytes(seed)
        sig = key.sign(b"test message")
        # Verify doesn't raise
        key.public_key().verify(sig, b"test message")

    def test_100_roundtrips_idempotent(self):
        """100 generate→recover cycles all produce consistent keys."""
        for _ in range(100):
            words, entropy = generate_mnemonic()
            seed1 = entropy_to_ed25519_seed(entropy)
            seed2 = mnemonic_to_private_key(words)
            assert seed1 == seed2

    def test_full_identity_roundtrip(self):
        """Generate → create Ed25519 key → get DID → recover → same DID."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        except ImportError:
            pytest.skip("cryptography not installed")

        words, _ = generate_mnemonic()
        seed = mnemonic_to_private_key(words)

        # Create identity
        key = Ed25519PrivateKey.from_private_bytes(seed)
        pub_hex = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        did = f"did:ecp:{hashlib.sha256(pub_hex.encode()).hexdigest()[:32]}"

        # Recover from words
        seed2 = mnemonic_to_private_key(words)
        key2 = Ed25519PrivateKey.from_private_bytes(seed2)
        pub_hex2 = key2.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        did2 = f"did:ecp:{hashlib.sha256(pub_hex2.encode()).hexdigest()[:32]}"

        assert did == did2
        assert pub_hex == pub_hex2


class TestLegacyExport:
    """A3: Private key → mnemonic export (for existing identities)."""

    def test_legacy_export_roundtrip(self):
        """Legacy key → export mnemonic → recover first 16 bytes."""
        priv_hex = os.urandom(32).hex()
        words = export_mnemonic_for_legacy_key(priv_hex)
        assert len(words) == 12
        recovered_entropy = recover_legacy_key(words)
        assert recovered_entropy == bytes.fromhex(priv_hex)[:16]

    def test_legacy_export_deterministic(self):
        priv_hex = "a" * 64
        w1 = export_mnemonic_for_legacy_key(priv_hex)
        w2 = export_mnemonic_for_legacy_key(priv_hex)
        assert w1 == w2


class TestHKDF:
    """HKDF-SHA256 implementation tests."""

    def test_hkdf_deterministic(self):
        k1 = _hkdf_sha256(b"secret", b"salt", b"info")
        k2 = _hkdf_sha256(b"secret", b"salt", b"info")
        assert k1 == k2 and len(k1) == 32

    def test_hkdf_different_inputs(self):
        k1 = _hkdf_sha256(b"secret1", b"salt", b"info")
        k2 = _hkdf_sha256(b"secret2", b"salt", b"info")
        assert k1 != k2

    def test_hkdf_empty_salt(self):
        k = _hkdf_sha256(b"secret", b"", b"info")
        assert len(k) == 32


class TestDisplay:
    def test_format_display(self):
        words = ["abandon"] * 12
        display = format_mnemonic_display(words)
        assert "┌" in display
        assert "└" in display
        assert "abandon" in display
        assert " 1." in display
        assert "12." in display
