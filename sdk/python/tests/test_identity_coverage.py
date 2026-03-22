"""Tests for identity.py coverage gaps — lines 22-23,54-55,72,76,87-98,113-115,139,143,149-150."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestNowMs:
    def test_returns_int(self):
        from atlast_ecp.identity import _now_ms
        ts = _now_ms()
        assert isinstance(ts, int)
        assert ts > 1_000_000_000_000  # reasonable ms timestamp


class TestResolveEcpDir:
    def test_uses_atlast_ecp_dir_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATLAST_ECP_DIR", str(tmp_path / "custom"))
        from atlast_ecp.identity import _resolve_ecp_dir
        result = _resolve_ecp_dir()
        assert str(result) == str(tmp_path / "custom")

    def test_uses_ecp_dir_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ATLAST_ECP_DIR", raising=False)
        monkeypatch.setenv("ECP_DIR", str(tmp_path / "ecp_fallback"))
        from atlast_ecp.identity import _resolve_ecp_dir
        result = _resolve_ecp_dir()
        assert str(result) == str(tmp_path / "ecp_fallback")


class TestGetOrCreateIdentity:
    def test_loads_existing_on_second_call(self, tmp_path):
        from atlast_ecp.identity import get_or_create_identity
        id1 = get_or_create_identity(ecp_dir=str(tmp_path))
        id2 = get_or_create_identity(ecp_dir=str(tmp_path))
        assert id1["did"] == id2["did"]

    def test_recreates_on_invalid_json(self, tmp_path):
        """If identity.json is corrupted, creates a new one."""
        ifile = tmp_path / "identity.json"
        ifile.write_text("{{invalid json")
        from atlast_ecp.identity import get_or_create_identity
        identity = get_or_create_identity(ecp_dir=str(tmp_path))
        assert identity["did"].startswith("did:ecp:")

    def test_uses_ecp_dir_param(self, tmp_path):
        from atlast_ecp.identity import get_or_create_identity
        sub = tmp_path / "mydir"
        identity = get_or_create_identity(ecp_dir=str(sub))
        assert (sub / "identity.json").exists()


class TestCreateIdentityFallback:
    def test_fallback_without_crypto(self, tmp_path):
        """Test identity creation when cryptography package unavailable."""
        import atlast_ecp.identity as id_mod
        original = id_mod.HAS_CRYPTO
        try:
            id_mod.HAS_CRYPTO = False
            from atlast_ecp.identity import _create_identity
            identity = _create_identity(tmp_path)
            assert identity["did"].startswith("did:ecp:")
            assert identity["verified"] is False
            assert len(identity["priv_key"]) == 64  # 32 bytes hex
        finally:
            id_mod.HAS_CRYPTO = original


class TestMaybeMigrateIdentity:
    def test_no_migration_if_no_crypto(self, tmp_path):
        import atlast_ecp.identity as id_mod
        original = id_mod.HAS_CRYPTO
        try:
            id_mod.HAS_CRYPTO = False
            from atlast_ecp.identity import _maybe_migrate_identity
            identity = {"did": "did:ecp:abc", "pub_key": "abcdef", "priv_key": "112233"}
            result = _maybe_migrate_identity(identity, tmp_path / "id.json")
            assert result is identity  # unchanged
        finally:
            id_mod.HAS_CRYPTO = original

    def test_no_migration_if_already_migrated(self, tmp_path):
        from atlast_ecp.identity import _maybe_migrate_identity
        identity = {
            "did": "did:ecp:abc",
            "pub_key": "abcdef",
            "priv_key": "112233",
            "crypto_pub_key": "existing",
        }
        result = _maybe_migrate_identity(identity, tmp_path / "id.json")
        assert result["crypto_pub_key"] == "existing"

    def test_no_migration_if_not_fallback_pub(self, tmp_path):
        """Identity with non-fallback pubkey should not be migrated."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            pytest.skip("cryptography not installed")

        import secrets, hashlib
        priv_hex = secrets.token_hex(32)
        # Use a random pub_key that does NOT equal sha256(priv_bytes)
        pub_hex = secrets.token_hex(32)

        ifile = tmp_path / "id.json"
        identity = {"did": "did:ecp:abc", "pub_key": pub_hex, "priv_key": priv_hex}
        from atlast_ecp.identity import _maybe_migrate_identity
        result = _maybe_migrate_identity(identity, ifile)
        # Should not migrate — pub_key is not sha256(priv_bytes)
        assert "crypto_pub_key" not in result

    def test_migrates_fallback_identity(self, tmp_path):
        """Identity with pub_key == sha256(priv_bytes) should be migrated."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            pytest.skip("cryptography not installed")

        import secrets, hashlib
        priv_hex = secrets.token_hex(32)
        pub_hex = hashlib.sha256(bytes.fromhex(priv_hex)).hexdigest()  # fallback pub

        ifile = tmp_path / "id.json"
        identity = {"did": "did:ecp:abc123", "pub_key": pub_hex, "priv_key": priv_hex}
        from atlast_ecp.identity import _maybe_migrate_identity
        result = _maybe_migrate_identity(identity, ifile)
        # Should migrate
        assert "crypto_pub_key" in result
        assert result["migrated_from_fallback"] is True
        assert result["did"] == "did:ecp:abc123"  # DID preserved
        assert ifile.exists()


class TestSign:
    def test_unverified_without_crypto(self):
        import atlast_ecp.identity as id_mod
        original = id_mod.HAS_CRYPTO
        try:
            id_mod.HAS_CRYPTO = False
            from atlast_ecp.identity import sign
            result = sign({"priv_key": "abc"}, "data")
            assert result == "unverified"
        finally:
            id_mod.HAS_CRYPTO = original

    def test_unverified_when_no_priv_key(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            pytest.skip("cryptography not installed")
        from atlast_ecp.identity import sign
        result = sign({}, "data")
        assert result == "unverified"

    def test_unverified_on_invalid_key(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            pytest.skip("cryptography not installed")
        from atlast_ecp.identity import sign
        # Invalid hex for priv_key — should catch exception and return unverified
        result = sign({"priv_key": "not_valid_hex!!!"}, "data")
        assert result == "unverified"

    def test_sign_with_crypto_priv_key(self, tmp_path):
        """Uses crypto_priv_key preferentially."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
        except ImportError:
            pytest.skip("cryptography not installed")
        pk = Ed25519PrivateKey.generate()
        priv_hex = pk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
        from atlast_ecp.identity import sign
        result = sign({"crypto_priv_key": priv_hex, "priv_key": "badhex"}, "hello")
        assert result.startswith("ed25519:")
