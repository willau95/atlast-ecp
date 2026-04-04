"""
Tests for ATLAST Proxy — unit tests (no real API calls).

Tests provider detection, upstream resolution, response parsing,
ECP recording, and proxy handler behavior.
"""

import json
import os
import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from atlast_ecp.proxy import (
    _detect_provider,
    _detect_action,
    _resolve_upstream,
    _extract_model_from_request,
    _extract_tokens_from_response,
    _reconstruct_sse_content,
    _find_free_port,
    ATLASTProxy,
    DEFAULT_UPSTREAMS,
    HAS_AIOHTTP,
)


# ─── Provider Detection ──────────────────────────────────────────────────────

class TestProviderDetection:
    def test_openai_chat_completions(self):
        assert _detect_provider("/v1/chat/completions") == "openai"

    def test_openai_completions(self):
        assert _detect_provider("/v1/completions") == "openai"

    def test_openai_embeddings(self):
        assert _detect_provider("/v1/embeddings") == "openai"

    def test_anthropic(self):
        assert _detect_provider("/v1/messages") == "anthropic"

    def test_gemini(self):
        assert _detect_provider("/v1beta/models/gemini-pro/generateContent") == "gemini"

    def test_minimax(self):
        assert _detect_provider("/v1/text/chatcompletion") == "minimax"

    def test_unknown_path(self):
        assert _detect_provider("/v2/something/else") == "unknown"

    def test_openai_compatible_deepseek(self):
        # DeepSeek uses the same /v1/chat/completions path
        assert _detect_provider("/v1/chat/completions") == "openai"


class TestActionDetection:
    def test_chat_completions(self):
        assert _detect_action("/v1/chat/completions") == "llm_call"

    def test_anthropic_messages(self):
        assert _detect_action("/v1/messages") == "llm_call"

    def test_embeddings(self):
        assert _detect_action("/v1/embeddings") == "tool_call"

    def test_gemini_generate(self):
        assert _detect_action("/v1beta/models/gemini-pro/generateContent") == "llm_call"

    def test_unknown_defaults_to_llm_call(self):
        assert _detect_action("/v2/something") == "llm_call"


# ─── Upstream Resolution ─────────────────────────────────────────────────────

class TestUpstreamResolution:
    def test_default_openai(self):
        assert _resolve_upstream({}, "openai") == "https://api.openai.com"

    def test_default_anthropic(self):
        assert _resolve_upstream({}, "anthropic") == "https://api.anthropic.com"

    def test_default_gemini(self):
        assert _resolve_upstream({}, "gemini") == "https://generativelanguage.googleapis.com"

    def test_explicit_header_override_allowed(self):
        # Only known upstream domains are accepted via header override
        headers = {"X-Real-API-URL": "https://api.openai.com/v2"}
        assert _resolve_upstream(headers, "openai") == "https://api.openai.com/v2"

    def test_explicit_header_override_blocked(self):
        # Unknown domains are rejected — falls through to default
        headers = {"X-Real-API-URL": "https://evil.example.com/"}
        assert _resolve_upstream(headers, "openai") == "https://api.openai.com"

    def test_env_var_override(self):
        with patch.dict(os.environ, {"ATLAST_UPSTREAM_URL": "https://my.proxy.com"}):
            assert _resolve_upstream({}, "openai") == "https://my.proxy.com"

    def test_unknown_provider_defaults_openai(self):
        assert _resolve_upstream({}, "unknown") == "https://api.openai.com"


# ─── Request/Response Parsing ─────────────────────────────────────────────────

class TestParsing:
    def test_extract_model_from_request(self):
        body = json.dumps({"model": "gpt-4o", "messages": []}).encode()
        assert _extract_model_from_request(body) == "gpt-4o"

    def test_extract_model_missing(self):
        body = json.dumps({"messages": []}).encode()
        assert _extract_model_from_request(body) == "unknown"

    def test_extract_model_invalid_json(self):
        assert _extract_model_from_request(b"not json") == "unknown"

    def test_extract_tokens_openai(self):
        body = json.dumps({
            "usage": {"prompt_tokens": 10, "completion_tokens": 20}
        }).encode()
        assert _extract_tokens_from_response(body, "openai") == (10, 20)

    def test_extract_tokens_anthropic(self):
        body = json.dumps({
            "usage": {"input_tokens": 15, "output_tokens": 25}
        }).encode()
        assert _extract_tokens_from_response(body, "anthropic") == (15, 25)

    def test_extract_tokens_invalid_json(self):
        assert _extract_tokens_from_response(b"bad", "openai") == (None, None)


# ─── SSE Reconstruction ──────────────────────────────────────────────────────

class TestSSEReconstruction:
    def test_openai_sse(self):
        chunks = (
            'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
            'data: [DONE]\n\n'
        ).encode()
        result = _reconstruct_sse_content(chunks, "openai")
        assert isinstance(result, dict)
        assert result["content"] == "Hello world"
        assert result["tool_calls"] == []

    def test_anthropic_sse(self):
        chunks = (
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n'
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" there"}}\n\n'
            'data: {"type":"message_stop"}\n\n'
        ).encode()
        result = _reconstruct_sse_content(chunks, "anthropic")
        assert result["content"] == "Hi there"

    def test_empty_chunks(self):
        result = _reconstruct_sse_content(b"", "openai")
        assert result["content"] == ""

    def test_malformed_sse(self):
        chunks = b"not: valid\nsse: data\n"
        result = _reconstruct_sse_content(chunks, "openai")
        # Should not crash, returns something
        assert isinstance(result["content"], str)

    def test_openai_sse_with_empty_deltas(self):
        chunks = (
            'data: {"choices":[{"delta":{}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            'data: [DONE]\n\n'
        ).encode()
        result = _reconstruct_sse_content(chunks, "openai")
        assert result["content"] == "ok"

    def test_openai_sse_tool_calls(self):
        """Tool calls in streaming should be extracted."""
        chunks = (
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"read_file","arguments":""}}]}}]}\n\n'
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"path\\": \\"test.py\\"}"}}]}}]}\n\n'
            'data: {"choices":[{"finish_reason":"tool_calls"}]}\n\n'
            'data: [DONE]\n\n'
        ).encode()
        result = _reconstruct_sse_content(chunks, "openai")
        assert result["stop_reason"] == "tool_calls"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read_file"
        assert result["content"] == ""

    def test_anthropic_sse_tool_use(self):
        """Anthropic tool_use blocks should be extracted."""
        chunks = (
            'data: {"type":"content_block_start","content_block":{"type":"tool_use","name":"write_file"}}\n\n'
            'data: {"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{\\"path\\": \\"x.py\\"}"}}\n\n'
            'data: {"type":"content_block_stop"}\n\n'
            'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"}}\n\n'
        ).encode()
        result = _reconstruct_sse_content(chunks, "anthropic")
        assert result["stop_reason"] == "tool_use"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "write_file"

    def test_sse_error_detection(self):
        """Provider errors in SSE should be detected."""
        chunks = (
            'data: {"type":"error","error":{"type":"invalid_request_error","message":"billing issue"}}\n\n'
        ).encode()
        result = _reconstruct_sse_content(chunks, "anthropic")
        assert result["is_error"] is True


# ─── Proxy Class ──────────────────────────────────────────────────────────────

class TestATLASTProxy:
    def test_creation(self):
        proxy = ATLASTProxy(port=9999, agent="test-proxy")
        assert proxy.port == 9999
        assert proxy.agent == "test-proxy"
        assert proxy.record_count == 0

    @pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
    def test_create_app(self):
        proxy = ATLASTProxy()
        app = proxy.create_app()
        assert app is not None


# ─── Utility ──────────────────────────────────────────────────────────────────

class TestUtility:
    def test_find_free_port(self):
        port = _find_free_port()
        assert isinstance(port, int)
        assert 1024 < port < 65536

    def test_find_free_port_returns_different_ports(self):
        ports = {_find_free_port() for _ in range(5)}
        # Should get at least 2 different ports
        assert len(ports) >= 2
