"""
Test: Library Mode — wrap(client)
Tests wrap() with mocked Anthropic and OpenAI clients.

Run: python -m pytest tests/test_library_mode.py -v
"""

import os
import sys
import time
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def temp_ecp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Reset core state between tests
    from atlast_ecp.core import reset
    reset()
    yield tmp_path


# ─── Mock Helpers ─────────────────────────────────────────────────────────────

def make_anthropic_client():
    """Create a mock Anthropic client."""
    client = MagicMock()
    client.__class__.__name__ = "Anthropic"
    client.__class__.__module__ = "anthropic"

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="The answer is 42.")]
    mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)

    client.messages.create = MagicMock(return_value=mock_response)
    return client, mock_response


def make_openai_client():
    """Create a mock OpenAI client."""
    client = MagicMock()
    client.__class__.__name__ = "OpenAI"
    client.__class__.__module__ = "openai"

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="The answer is 42."))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    client.chat.completions.create = MagicMock(return_value=mock_response)
    return client, mock_response


# ─── Tests: Anthropic wrap ────────────────────────────────────────────────────

class TestAnthropicWrap:
    def test_wrap_returns_client(self):
        from atlast_ecp.wrap import wrap
        client, _ = make_anthropic_client()
        wrapped = wrap(client)
        assert wrapped is client  # Returns same client object

    def test_original_response_unchanged(self):
        from atlast_ecp.wrap import wrap
        client, mock_response = make_anthropic_client()
        wrapped = wrap(client)

        result = wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "What is 6x7?"}]
        )
        assert result is mock_response  # Response unchanged

    def test_ecp_record_created(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello"}]
        )
        time.sleep(0.2)  # Wait for async thread

        records = load_records(limit=10)
        assert len(records) >= 1

    def test_record_type_is_llm_call(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello"}]
        )
        time.sleep(0.2)

        records = load_records(limit=1)
        assert records[0]["step"]["type"] == "llm_call"

    def test_record_has_model(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello"}]
        )
        time.sleep(0.2)

        records = load_records(limit=1)
        assert records[0]["step"].get("model") == "claude-3-5-sonnet-20241022"

    def test_record_has_tokens(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello"}]
        )
        time.sleep(0.2)

        records = load_records(limit=1)
        step = records[0]["step"]
        assert step.get("tokens_in") == 10
        assert step.get("tokens_out") == 5

    def test_hash_format(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello"}]
        )
        time.sleep(0.2)

        records = load_records(limit=1)
        step = records[0]["step"]
        assert step["in_hash"].startswith("sha256:")
        assert step["out_hash"].startswith("sha256:")

    def test_genesis_chain_prev(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "First call"}]
        )
        time.sleep(0.2)

        records = load_records(limit=1)
        assert records[0]["chain"]["prev"] == "genesis"

    def test_chain_links_two_calls(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        wrapped.messages.create(model="m", max_tokens=10,
                                messages=[{"role": "user", "content": "First"}])
        time.sleep(0.2)
        wrapped.messages.create(model="m", max_tokens=10,
                                messages=[{"role": "user", "content": "Second"}])
        time.sleep(0.2)

        records = load_records(limit=10)
        assert len(records) == 2
        # Second record's prev = first record's id
        # Records come newest-first, so records[0] is second call
        assert records[0]["chain"]["prev"] == records[1]["id"]

    def test_no_confidence_field(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        wrapped.messages.create(model="m", max_tokens=10,
                                messages=[{"role": "user", "content": "Test"}])
        time.sleep(0.2)

        records = load_records(limit=1)
        assert "confidence" not in records[0]
        assert "confidence" not in records[0].get("step", {})

    def test_fail_open_on_bad_client(self):
        """wrap() must return original client if something goes wrong."""
        from atlast_ecp.wrap import wrap
        bad_client = object()  # Not a real LLM client
        result = wrap(bad_client)
        assert result is bad_client  # Fail-open: return original

    def test_retry_detected(self):
        """Same input hash twice → second call gets retried flag."""
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_anthropic_client()
        wrapped = wrap(client)

        same_messages = [{"role": "user", "content": "Identical question"}]
        wrapped.messages.create(model="m", max_tokens=10, messages=same_messages)
        time.sleep(0.1)
        wrapped.messages.create(model="m", max_tokens=10, messages=same_messages)
        time.sleep(0.2)

        records = load_records(limit=10)
        # Second call (records[0] is newest) should have retried flag
        assert "retried" in records[0]["step"]["flags"]


# ─── Tests: OpenAI wrap ───────────────────────────────────────────────────────

class TestOpenAIWrap:
    def test_wrap_returns_client(self):
        from atlast_ecp.wrap import wrap
        client, _ = make_openai_client()
        wrapped = wrap(client)
        assert wrapped is client

    def test_original_response_unchanged(self):
        from atlast_ecp.wrap import wrap
        client, mock_response = make_openai_client()
        wrapped = wrap(client)

        result = wrapped.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert result is mock_response

    def test_ecp_record_created(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_openai_client()
        wrapped = wrap(client)

        wrapped.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}]
        )
        time.sleep(0.2)

        records = load_records(limit=10)
        assert len(records) >= 1

    def test_record_type_is_llm_call(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        client, _ = make_openai_client()
        wrapped = wrap(client)

        wrapped.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}]
        )
        time.sleep(0.2)

        records = load_records(limit=1)
        assert records[0]["step"]["type"] == "llm_call"
