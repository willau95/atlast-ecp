"""Tests for config.py coverage gaps — lines 19,27-29,55,71-75,80-84."""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch


class TestGetConfigPath:
    def test_returns_path_object(self):
        from atlast_ecp.config import get_config_path
        p = get_config_path()
        assert isinstance(p, Path)
        assert p.name == "config.json"


class TestLoadConfig:
    def test_returns_empty_if_no_file(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "nonexistent.json")
        from atlast_ecp.config import load_config
        assert load_config() == {}

    def test_returns_empty_on_invalid_json(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        bad = tmp_path / "config.json"
        bad.write_text("not valid json {{")
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", bad)
        from atlast_ecp.config import load_config
        assert load_config() == {}

    def test_loads_valid_config(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"endpoint": "https://example.com", "agent_api_key": "key123"}))
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_file)
        from atlast_ecp.config import load_config
        result = load_config()
        assert result["endpoint"] == "https://example.com"
        assert result["agent_api_key"] == "key123"


class TestSaveConfig:
    def test_creates_dir_and_saves(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        cfg_dir = tmp_path / "atlast"
        cfg_file = cfg_dir / "config.json"
        monkeypatch.setattr(cfg_mod, "CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_file)
        from atlast_ecp.config import save_config
        save_config({"agent_api_key": "mykey"})
        assert cfg_file.exists()
        data = json.loads(cfg_file.read_text())
        assert data["agent_api_key"] == "mykey"

    def test_merges_with_existing(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        cfg_dir = tmp_path / "atlast"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "config.json"
        cfg_file.write_text(json.dumps({"endpoint": "https://old.com", "existing_key": "value"}))
        monkeypatch.setattr(cfg_mod, "CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_file)
        from atlast_ecp.config import save_config
        save_config({"agent_api_key": "newkey"})
        data = json.loads(cfg_file.read_text())
        assert data["existing_key"] == "value"
        assert data["agent_api_key"] == "newkey"


class TestGetApiUrl:
    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("ATLAST_API_URL", "https://env.example.com/")
        from atlast_ecp.config import get_api_url
        assert get_api_url() == "https://env.example.com"

    def test_config_endpoint_fallback(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"endpoint": "https://config.example.com/"}))
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_file)
        monkeypatch.delenv("ATLAST_API_URL", raising=False)
        from atlast_ecp.config import get_api_url
        assert get_api_url() == "https://config.example.com"

    def test_default_empty_when_nothing_set(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "none.json")
        monkeypatch.delenv("ATLAST_API_URL", raising=False)
        from atlast_ecp.config import get_api_url, DEFAULT_ENDPOINT
        assert get_api_url() == DEFAULT_ENDPOINT


class TestGetApiKey:
    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("ATLAST_API_KEY", "env-key-123")
        from atlast_ecp.config import get_api_key
        assert get_api_key() == "env-key-123"

    def test_config_fallback(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"agent_api_key": "cfg-key-456"}))
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_file)
        monkeypatch.delenv("ATLAST_API_KEY", raising=False)
        from atlast_ecp.config import get_api_key
        assert get_api_key() == "cfg-key-456"

    def test_returns_none_when_nothing(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "none.json")
        monkeypatch.delenv("ATLAST_API_KEY", raising=False)
        from atlast_ecp.config import get_api_key
        assert get_api_key() is None


class TestGetWebhookUrl:
    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("ECP_WEBHOOK_URL", "https://hook.example.com/")
        from atlast_ecp.config import get_webhook_url
        assert get_webhook_url() == "https://hook.example.com"

    def test_config_fallback(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"webhook_url": "https://hook.cfg.com"}))
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_file)
        monkeypatch.delenv("ECP_WEBHOOK_URL", raising=False)
        from atlast_ecp.config import get_webhook_url
        assert get_webhook_url() == "https://hook.cfg.com"

    def test_returns_none_when_nothing(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "none.json")
        monkeypatch.delenv("ECP_WEBHOOK_URL", raising=False)
        from atlast_ecp.config import get_webhook_url
        assert get_webhook_url() is None


class TestGetWebhookToken:
    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("ECP_WEBHOOK_TOKEN", "tok123")
        from atlast_ecp.config import get_webhook_token
        assert get_webhook_token() == "tok123"

    def test_config_fallback(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"webhook_token": "cfg-token"}))
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_file)
        monkeypatch.delenv("ECP_WEBHOOK_TOKEN", raising=False)
        from atlast_ecp.config import get_webhook_token
        assert get_webhook_token() == "cfg-token"

    def test_returns_none_when_nothing(self, tmp_path, monkeypatch):
        from atlast_ecp import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "none.json")
        monkeypatch.delenv("ECP_WEBHOOK_TOKEN", raising=False)
        from atlast_ecp.config import get_webhook_token
        assert get_webhook_token() is None
