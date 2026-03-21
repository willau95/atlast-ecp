"""
ATLAST Local Config — ~/.atlast/config.json

Stores agent_did, agent_api_key, endpoint after registration.
Priority for all settings: CLI args > env vars > config file > defaults.
"""

import json
import os
from pathlib import Path
from typing import Optional

DEFAULT_ENDPOINT = ""  # No default — user must configure via ATLAST_API_URL env or atlast init
CONFIG_DIR = Path.home() / ".atlast"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_config_path() -> Path:
    return CONFIG_FILE


def load_config() -> dict:
    """Load local config. Returns {} if not exists or invalid."""
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}


def save_config(data: dict):
    """
    Save config to ~/.atlast/config.json. Creates dir if needed.
    Note: load-merge-write is NOT atomic. Safe for single-process CLI use.
    Multi-process safety would require file locking (not needed for Phase 1).
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Merge with existing
    existing = load_config()
    existing.update(data)
    CONFIG_FILE.write_text(json.dumps(existing, indent=2))


def get_api_url() -> str:
    """
    Get API URL with priority: env ATLAST_API_URL > config endpoint > default.
    """
    env_url = os.environ.get("ATLAST_API_URL")
    if env_url:
        return env_url.rstrip("/")
    cfg = load_config()
    if cfg.get("endpoint"):
        return cfg["endpoint"].rstrip("/")
    return DEFAULT_ENDPOINT


def get_api_key() -> Optional[str]:
    """
    Get API key with priority: env ATLAST_API_KEY > config agent_api_key > None.
    """
    env_key = os.environ.get("ATLAST_API_KEY")
    if env_key:
        return env_key
    cfg = load_config()
    return cfg.get("agent_api_key") or None


def get_webhook_url() -> Optional[str]:
    """Get webhook URL: env ECP_WEBHOOK_URL > config webhook_url > None."""
    env = os.environ.get("ECP_WEBHOOK_URL")
    if env:
        return env.rstrip("/")
    cfg = load_config()
    return cfg.get("webhook_url") or None


def get_webhook_token() -> Optional[str]:
    """Get webhook token: env ECP_WEBHOOK_TOKEN > config webhook_token > None."""
    env = os.environ.get("ECP_WEBHOOK_TOKEN")
    if env:
        return env
    cfg = load_config()
    return cfg.get("webhook_token") or None
