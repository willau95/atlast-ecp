"""Tests for proxy.py coverage gaps — lines 43-44, create_app, entry point helpers."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ─── HAS_AIOHTTP flag ────────────────────────────────────────────────────────

class TestHasAiohttp:
    def test_has_aiohttp_is_bool(self):
        from atlast_ecp.proxy import HAS_AIOHTTP
        assert isinstance(HAS_AIOHTTP, bool)


# ─── _resolve_upstream with more env vars ────────────────────────────────────

class TestResolveUpstreamEnvVars:
    def test_atlast_openai_upstream(self, monkeypatch):
        monkeypatch.delenv("ATLAST_UPSTREAM_URL", raising=False)
        monkeypatch.setenv("ATLAST_OPENAI_UPSTREAM", "https://my-openai.example.com")
        from atlast_ecp.proxy import _resolve_upstream
        assert _resolve_upstream({}, "openai") == "https://my-openai.example.com"

    def test_openai_api_base_env(self, monkeypatch):
        monkeypatch.delenv("ATLAST_UPSTREAM_URL", raising=False)
        monkeypatch.delenv("ATLAST_OPENAI_UPSTREAM", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", "https://openai-base.example.com")
        from atlast_ecp.proxy import _resolve_upstream
        assert _resolve_upstream({}, "openai") == "https://openai-base.example.com"

    def test_lowercase_header(self, monkeypatch):
        # Test lowercase header key — must use an allowed upstream domain
        from atlast_ecp.proxy import _resolve_upstream
        headers = {"x-real-api-url": "https://api.anthropic.com/v2"}
        assert _resolve_upstream(headers, "openai") == "https://api.anthropic.com/v2"

    def test_default_minimax(self, monkeypatch):
        for var in ["ATLAST_UPSTREAM_URL", "ATLAST_OPENAI_UPSTREAM", "ATLAST_ANTHROPIC_UPSTREAM",
                    "OPENAI_API_BASE", "OPENAI_BASE_URL_ORIGINAL", "ANTHROPIC_BASE_URL_ORIGINAL"]:
            monkeypatch.delenv(var, raising=False)
        from atlast_ecp.proxy import _resolve_upstream
        assert _resolve_upstream({}, "minimax") == "https://api.minimax.chat"


# ─── _extract_tokens_from_response edge cases ────────────────────────────────

class TestExtractTokensEdgeCases:
    def test_gemini_provider_returns_none(self):
        body = json.dumps({"usage": {"promptTokenCount": 10}}).encode()
        from atlast_ecp.proxy import _extract_tokens_from_response
        result = _extract_tokens_from_response(body, "gemini")
        assert result == (None, None)

    def test_missing_usage_field(self):
        body = json.dumps({"choices": []}).encode()
        from atlast_ecp.proxy import _extract_tokens_from_response
        tin, tout = _extract_tokens_from_response(body, "openai")
        assert tin is None
        assert tout is None


# ─── _reconstruct_sse_content edge cases ────────────────────────────────────

class TestSSEEdgeCases:
    def test_minimax_streaming(self):
        chunks = (
            'data: {"choices":[{"delta":{"content":"MiniMax"}}]}\n\n'
            'data: [DONE]\n\n'
        ).encode()
        from atlast_ecp.proxy import _reconstruct_sse_content
        result = _reconstruct_sse_content(chunks, "minimax")
        assert result["content"] == "MiniMax"

    def test_anthropic_non_delta_events_skipped(self):
        chunks = (
            'data: {"type":"message_start","message":{}}\n\n'
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n'
        ).encode()
        from atlast_ecp.proxy import _reconstruct_sse_content
        result = _reconstruct_sse_content(chunks, "anthropic")
        assert result["content"] == "Hi"

    def test_invalid_json_in_sse_lines_skipped(self):
        chunks = (
            'data: {bad json}\n\n'
            'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
        ).encode()
        from atlast_ecp.proxy import _reconstruct_sse_content
        result = _reconstruct_sse_content(chunks, "openai")
        assert result["content"] == "ok"


# ─── _record_ecp ─────────────────────────────────────────────────────────────

class TestRecordEcp:
    def test_fires_and_forgets_without_crash(self):
        """_record_ecp should not raise even if core.record_minimal is unavailable."""
        import threading
        done = threading.Event()

        original_target = None

        def mock_thread_start(self_t):
            self_t._target(*self_t._args, **self_t._kwargs)
            done.set()

        with patch("atlast_ecp.proxy.threading.Thread") as MockThread:
            mock_t = MagicMock()
            MockThread.return_value = mock_t

            from atlast_ecp.proxy import _record_ecp
            _record_ecp(b'{"model":"gpt-4"}', "response", "/v1/chat/completions",
                        "openai", "test-agent", "gpt-4", 150, 10, 20)
            mock_t.start.assert_called_once()

    def test_does_not_raise_on_import_error(self):
        """Even if record_minimal raises, the thread completes silently."""
        import sys
        from atlast_ecp.proxy import _record_ecp
        # Should not raise
        with patch("atlast_ecp.core.record_minimal", side_effect=Exception("fail")):
            _record_ecp(b"{}", "resp", "/v1/messages", "anthropic", "agent", "claude", 100)
        # If we got here, it's fine


# ─── ATLASTProxy.create_app ──────────────────────────────────────────────────

class TestCreateApp:
    def test_create_app_returns_app(self):
        from atlast_ecp.proxy import HAS_AIOHTTP, ATLASTProxy
        if not HAS_AIOHTTP:
            pytest.skip("aiohttp not installed")
        proxy = ATLASTProxy(port=9123, agent="test")
        app = proxy.create_app()
        assert app is not None
        assert proxy._app is app


# ─── run_proxy when aiohttp not available ────────────────────────────────────

class TestRunProxyNoAiohttp:
    def test_exits_when_aiohttp_missing(self):
        import atlast_ecp.proxy as proxy_mod
        original = proxy_mod.HAS_AIOHTTP
        try:
            proxy_mod.HAS_AIOHTTP = False
            from atlast_ecp.proxy import run_proxy
            with pytest.raises(SystemExit):
                run_proxy()
        finally:
            proxy_mod.HAS_AIOHTTP = original


class TestRunWithProxyNoAiohttp:
    def test_exits_when_aiohttp_missing(self):
        import atlast_ecp.proxy as proxy_mod
        original = proxy_mod.HAS_AIOHTTP
        try:
            proxy_mod.HAS_AIOHTTP = False
            from atlast_ecp.proxy import run_with_proxy
            with pytest.raises(SystemExit):
                run_with_proxy(["echo", "hello"])
        finally:
            proxy_mod.HAS_AIOHTTP = original


# ─── _find_free_port ────────────────────────────────────────────────────────

class TestFindFreePort:
    def test_returns_valid_port(self):
        from atlast_ecp.proxy import _find_free_port
        port = _find_free_port()
        assert 1024 < port < 65536
