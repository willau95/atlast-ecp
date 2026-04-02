"""
ATLAST Vault Backup — AES-256-GCM encrypted backup of raw content.

Each vault entry is independently encrypted with a key derived from
the agent's Ed25519 private key + record_id (via HKDF).

Backup files: {backup_path}/ecp-vault/{record_id}.enc
Format: 12-byte nonce + ciphertext + 16-byte GCM tag (all concatenated)
"""

import json
import os
import platform
from pathlib import Path
from typing import Optional

from .recovery import _hkdf_sha256

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_AESGCM = True
except ImportError:
    HAS_AESGCM = False


def _derive_vault_key(priv_key_hex: str, record_id: str) -> bytes:
    """Derive per-record AES-256 key from private key + record_id."""
    return _hkdf_sha256(
        ikm=bytes.fromhex(priv_key_hex),
        salt=b"atlast-vault-backup-v1",
        info=record_id.encode("utf-8"),
        length=32,
    )


def encrypt_vault_entry(record_id: str, content_json: str, priv_key_hex: str) -> bytes:
    """
    Encrypt a vault entry.

    Returns: nonce (12B) + ciphertext + tag (16B)
    """
    if not HAS_AESGCM:
        raise RuntimeError("cryptography package required for vault backup")

    key = _derive_vault_key(priv_key_hex, record_id)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, content_json.encode("utf-8"), None)
    return nonce + ct  # nonce(12) + ciphertext + tag(16)


def decrypt_vault_entry(encrypted: bytes, record_id: str, priv_key_hex: str) -> dict:
    """
    Decrypt a vault entry.

    Returns: {"input": "...", "output": "..."}
    Raises: ValueError if key is wrong or data is tampered.
    """
    if not HAS_AESGCM:
        raise RuntimeError("cryptography package required for vault backup")
    if len(encrypted) < 28:  # 12 nonce + 16 tag minimum
        raise ValueError("Encrypted data too short")

    key = _derive_vault_key(priv_key_hex, record_id)
    nonce = encrypted[:12]
    ct = encrypted[12:]

    try:
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ct, None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Decryption failed (wrong key or corrupted data): {e}")


def backup_vault_entry(
    record_id: str,
    content_json: str,
    backup_path: str,
    priv_key_hex: str,
) -> bool:
    """
    Encrypt and save a single vault entry to backup location.

    Returns True on success, False on failure (Fail-Open).
    """
    try:
        encrypted = encrypt_vault_entry(record_id, content_json, priv_key_hex)
        vault_dir = Path(backup_path) / "ecp-vault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        (vault_dir / f"{record_id}.enc").write_bytes(encrypted)
        return True
    except Exception:
        return False  # Fail-Open


def restore_vault_entries(
    backup_path: str,
    priv_key_hex: str,
    ecp_dir: Optional[str] = None,
) -> tuple[int, int]:
    """
    Restore all vault entries from backup to local ~/.ecp/vault/.

    Returns: (restored_count, error_count)
    """
    vault_backup_dir = Path(backup_path) / "ecp-vault"
    if not vault_backup_dir.exists():
        return 0, 0

    target_dir = Path(ecp_dir or os.path.expanduser("~/.ecp")) / "vault"
    target_dir.mkdir(parents=True, exist_ok=True)

    restored = 0
    errors = 0

    for enc_file in vault_backup_dir.glob("*.enc"):
        record_id = enc_file.stem  # filename without .enc
        try:
            encrypted = enc_file.read_bytes()
            content = decrypt_vault_entry(encrypted, record_id, priv_key_hex)
            target_file = target_dir / f"{record_id}.json"
            target_file.write_text(json.dumps(content, ensure_ascii=False))
            restored += 1
        except Exception:
            errors += 1

    return restored, errors


def backup_all_vault(
    ecp_dir: Optional[str] = None,
    backup_path: Optional[str] = None,
    priv_key_hex: Optional[str] = None,
) -> tuple[int, int]:
    """
    Backup entire vault directory to encrypted backup location.

    Returns: (backed_up_count, error_count)
    """
    ecp = Path(ecp_dir or os.path.expanduser("~/.ecp"))
    vault_dir = ecp / "vault"
    if not vault_dir.exists():
        return 0, 0

    if not backup_path or not priv_key_hex:
        return 0, 0

    backed_up = 0
    errors = 0

    for vault_file in vault_dir.glob("*.json"):
        record_id = vault_file.stem
        try:
            content_json = vault_file.read_text(encoding="utf-8")
            if backup_vault_entry(record_id, content_json, backup_path, priv_key_hex):
                backed_up += 1
            else:
                errors += 1
        except Exception:
            errors += 1

    return backed_up, errors


def detect_backup_locations() -> list[dict]:
    """
    Auto-detect available cloud sync folders on the system.

    Returns list of {name, path, available} dicts.
    """
    system = platform.system()
    home = Path.home()
    locations = []

    # iCloud (macOS)
    if system == "Darwin":
        icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        locations.append({
            "name": "iCloud Drive",
            "path": str(icloud / "ATLAST-Backup"),
            "available": icloud.exists(),
        })

    # Dropbox
    dropbox = home / "Dropbox"
    locations.append({
        "name": "Dropbox",
        "path": str(dropbox / "ATLAST-Backup"),
        "available": dropbox.exists(),
    })

    # OneDrive
    onedrive = home / "OneDrive"
    locations.append({
        "name": "OneDrive",
        "path": str(onedrive / "ATLAST-Backup"),
        "available": onedrive.exists(),
    })

    # Google Drive (various locations)
    for gd_name in ["Google Drive", "My Drive", "GoogleDrive"]:
        gd = home / gd_name
        if gd.exists():
            locations.append({
                "name": "Google Drive",
                "path": str(gd / "ATLAST-Backup"),
                "available": True,
            })
            break

    return locations
