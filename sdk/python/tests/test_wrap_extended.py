"""
Tests for extended wrap() support: Gemini, LiteLLM, edge cases.
"""

import os
import sys
import time
import types
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def temp_ecp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from atlast_ecp.core import reset
    reset()
    yield tmp_path


# ─── Gemini Mock ──────────────────────────────────────────────────────────────

class MockUsageMetadata:
    prompt_token_count = 10
    candidates_token_count = 20


class MockGeminiResponse:
    text = "The answer is 42."
    usage_metadata = MockUsageMetadata()


class MockGenerativeModel:
    __module__ = "google.generativeai.generative_models"
    model_name = "gemini-pro"

    def generate_content(self, contents, **kwargs):
        return MockGeminiResponse()


class TestGeminiWrap:
    def test_wrap_returns_model(self):
        from atlast_ecp.wrap import wrap
        model = MockGenerativeModel()
        wrapped = wrap(model)
        assert wrapped is model  # Same instance, patched in-place

    def test_response_unchanged(self):
        from atlast_ecp.wrap import wrap
        model = wrap(MockGenerativeModel())
        resp = model.generate_content("What is 6*7?")
        assert resp.text == "The answer is 42."

    def test_ecp_record_created(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        model = wrap(MockGenerativeModel())
        model.generate_content("What is 6*7?")
        time.sleep(0.3)
        records = load_records(limit=10)
        assert len(records) >= 1

    def test_record_has_model(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        model = wrap(MockGenerativeModel())
        model.generate_content("test")
        time.sleep(0.3)
        records = load_records(limit=1)
        assert records[0]["step"]["model"] == "gemini-pro"

    def test_record_has_tokens(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        model = wrap(MockGenerativeModel())
        model.generate_content("test")
        time.sleep(0.3)
        records = load_records(limit=1)
        assert records[0]["step"]["tokens_in"] == 10
        assert records[0]["step"]["tokens_out"] == 20


# ─── LiteLLM Mock ────────────────────────────────────────────────────────────

class MockLiteLLMChoice:
    def __init__(self):
        self.message = types.SimpleNamespace(content="LiteLLM response", role="assistant")


class MockLiteLLMUsage:
    prompt_tokens = 15
    completion_tokens = 25


class MockLiteLLMResponse:
    def __init__(self):
        self.choices = [MockLiteLLMChoice()]
        self.usage = MockLiteLLMUsage()


def _mock_litellm_module():
    """Create a mock litellm module."""
    mod = types.ModuleType("litellm")
    mod.__name__ = "litellm"

    def completion(*args, **kwargs):
        return MockLiteLLMResponse()

    async def acompletion(*args, **kwargs):
        return MockLiteLLMResponse()

    mod.completion = completion
    mod.acompletion = acompletion
    return mod


class TestLiteLLMWrap:
    def test_wrap_returns_module(self):
        from atlast_ecp.wrap import wrap
        mod = _mock_litellm_module()
        wrapped = wrap(mod)
        assert wrapped is mod

    def test_response_unchanged(self):
        from atlast_ecp.wrap import wrap
        mod = wrap(_mock_litellm_module())
        resp = mod.completion(model="gpt-4", messages=[{"role": "user", "content": "hi"}])
        assert resp.choices[0].message.content == "LiteLLM response"

    def test_ecp_record_created(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        mod = wrap(_mock_litellm_module())
        mod.completion(model="gpt-4", messages=[{"role": "user", "content": "hi"}])
        time.sleep(0.3)
        records = load_records(limit=10)
        assert len(records) >= 1

    def test_record_model_is_litellm(self):
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        mod = wrap(_mock_litellm_module())
        mod.completion(model="claude-3-sonnet", messages=[{"role": "user", "content": "hi"}])
        time.sleep(0.3)
        records = load_records(limit=1)
        assert records[0]["step"]["model"] == "claude-3-sonnet"


# ─── Edge Cases ───────────────────────────────────────────────────────────────

class TestWrapEdgeCases:
    def test_unknown_client_returns_unchanged(self):
        from atlast_ecp.wrap import wrap
        obj = {"not": "a client"}
        assert wrap(obj) is obj

    def test_none_returns_none(self):
        from atlast_ecp.wrap import wrap
        assert wrap(None) is None

    def test_string_returns_string(self):
        from atlast_ecp.wrap import wrap
        assert wrap("hello") == "hello"

    def test_double_wrap_is_safe(self):
        """Wrapping twice should not break anything."""
        from atlast_ecp.wrap import wrap
        from atlast_ecp.storage import load_records
        model = MockGenerativeModel()
        wrapped1 = wrap(model)
        wrapped2 = wrap(wrapped1)
        resp = wrapped2.generate_content("test")
        assert resp.text == "The answer is 42."
