"""Tests for ATLAST Vault Backup — AES-256-GCM encryption."""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from atlast_ecp.vault_backup import (
    encrypt_vault_entry,
    decrypt_vault_entry,
    backup_vault_entry,
    restore_vault_entries,
    backup_all_vault,
    detect_backup_locations,
    _derive_vault_key,
)


PRIV_KEY = "a" * 64  # Test private key


class TestEncryption:
    """B1: AES-256-GCM encryption engine."""

    def test_encrypt_decrypt_roundtrip(self):
        content = json.dumps({"input": "hello", "output": "world"})
        encrypted = encrypt_vault_entry("rec_001", content, PRIV_KEY)
        decrypted = decrypt_vault_entry(encrypted, "rec_001", PRIV_KEY)
        assert decrypted == {"input": "hello", "output": "world"}

    def test_different_record_ids_different_ciphertext(self):
        content = json.dumps({"input": "same", "output": "same"})
        e1 = encrypt_vault_entry("rec_001", content, PRIV_KEY)
        e2 = encrypt_vault_entry("rec_002", content, PRIV_KEY)
        assert e1 != e2  # Different keys per record

    def test_wrong_key_fails(self):
        content = json.dumps({"input": "secret", "output": "data"})
        encrypted = encrypt_vault_entry("rec_001", content, PRIV_KEY)
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_vault_entry(encrypted, "rec_001", "b" * 64)

    def test_wrong_record_id_fails(self):
        content = json.dumps({"input": "x", "output": "y"})
        encrypted = encrypt_vault_entry("rec_001", content, PRIV_KEY)
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_vault_entry(encrypted, "rec_002", PRIV_KEY)

    def test_tampered_data_fails(self):
        content = json.dumps({"input": "x", "output": "y"})
        encrypted = bytearray(encrypt_vault_entry("rec_001", content, PRIV_KEY))
        encrypted[-1] ^= 0xFF  # Flip last byte
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_vault_entry(bytes(encrypted), "rec_001", PRIV_KEY)

    def test_too_short_data(self):
        with pytest.raises(ValueError, match="too short"):
            decrypt_vault_entry(b"\x00" * 10, "rec_001", PRIV_KEY)

    def test_unicode_content(self):
        content = json.dumps({"input": "你好世界 🚀", "output": "こんにちは"}, ensure_ascii=False)
        encrypted = encrypt_vault_entry("rec_u", content, PRIV_KEY)
        decrypted = decrypt_vault_entry(encrypted, "rec_u", PRIV_KEY)
        assert decrypted["input"] == "你好世界 🚀"

    def test_large_content(self):
        big = "x" * 100_000
        content = json.dumps({"input": big, "output": big})
        encrypted = encrypt_vault_entry("rec_big", content, PRIV_KEY)
        decrypted = decrypt_vault_entry(encrypted, "rec_big", PRIV_KEY)
        assert decrypted["input"] == big

    def test_per_record_key_derivation(self):
        k1 = _derive_vault_key(PRIV_KEY, "rec_001")
        k2 = _derive_vault_key(PRIV_KEY, "rec_002")
        assert k1 != k2
        assert len(k1) == 32


class TestBackupRestore:
    """B2: Backup directory management."""

    def test_backup_and_restore(self):
        with tempfile.TemporaryDirectory() as backup_dir, \
             tempfile.TemporaryDirectory() as ecp_dir:
            # Backup
            content = json.dumps({"input": "test", "output": "data"})
            ok = backup_vault_entry("rec_001", content, backup_dir, PRIV_KEY)
            assert ok
            assert (os.path.join(backup_dir, "ecp-vault", "rec_001.enc"))

            # Restore
            restored, errors = restore_vault_entries(backup_dir, PRIV_KEY, ecp_dir)
            assert restored == 1
            assert errors == 0

            # Verify
            restored_file = os.path.join(ecp_dir, "vault", "rec_001.json")
            assert os.path.exists(restored_file)
            data = json.loads(open(restored_file).read())
            assert data == {"input": "test", "output": "data"}

    def test_backup_multiple(self):
        with tempfile.TemporaryDirectory() as backup_dir, \
             tempfile.TemporaryDirectory() as ecp_dir:
            for i in range(10):
                content = json.dumps({"input": f"in_{i}", "output": f"out_{i}"})
                backup_vault_entry(f"rec_{i:03d}", content, backup_dir, PRIV_KEY)

            restored, errors = restore_vault_entries(backup_dir, PRIV_KEY, ecp_dir)
            assert restored == 10
            assert errors == 0

    def test_backup_nonexistent_path_failopen(self):
        ok = backup_vault_entry("rec_001", '{"x":1}', "/nonexistent/path/xyz", PRIV_KEY)
        # Should not crash, returns False
        assert ok is False

    def test_restore_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            restored, errors = restore_vault_entries(d, PRIV_KEY)
            assert restored == 0 and errors == 0

    def test_backup_all_vault(self):
        with tempfile.TemporaryDirectory() as ecp_dir, \
             tempfile.TemporaryDirectory() as backup_dir:
            # Create some vault files
            vault_dir = os.path.join(ecp_dir, "vault")
            os.makedirs(vault_dir)
            for i in range(5):
                with open(os.path.join(vault_dir, f"rec_{i:03d}.json"), "w") as f:
                    json.dump({"input": f"in_{i}", "output": f"out_{i}"}, f)

            backed, errors = backup_all_vault(ecp_dir, backup_dir, PRIV_KEY)
            assert backed == 5
            assert errors == 0

            # Verify encrypted files exist
            enc_dir = os.path.join(backup_dir, "ecp-vault")
            assert len(os.listdir(enc_dir)) == 5


class TestDetection:
    """B3: Cloud storage auto-detection."""

    def test_returns_list(self):
        locations = detect_backup_locations()
        assert isinstance(locations, list)
        for loc in locations:
            assert "name" in loc
            assert "path" in loc
            assert "available" in loc
