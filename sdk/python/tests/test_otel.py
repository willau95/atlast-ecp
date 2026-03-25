"""
Tests for OTel auto-instrumentation (init() + ECPSpanExporter).
Tests use mocks — no real OTel or LLM libraries required.
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
    from atlast_ecp.auto import reset as auto_reset
    auto_reset()
    yield tmp_path


# ─── ECPSpanExporter Tests (with mock spans) ─────────────────────────────────

class TestECPSpanExporter:
    """Test the exporter directly with mock OTel spans."""

    def _make_exporter(self):
        """Create exporter or skip if OTel not installed."""
        try:
            from atlast_ecp.otel_exporter import ECPSpanExporter, HAS_OTEL
            if not HAS_OTEL:
                pytest.skip("opentelemetry-sdk not installed")
            return ECPSpanExporter()
        except ImportError:
            pytest.skip("opentelemetry-sdk not installed")

    def _make_span(self, attributes=None, name="test_span", duration_ms=100):
        """Create a mock OTel span."""
        start_ns = 1_000_000_000_000  # 1 second in ns
        end_ns = start_ns + (duration_ms * 1_000_000)

        class MockSpan:
            def __init__(self):
                self.name = name
                self.attributes = attributes or {}
                self.start_time = start_ns
                self.end_time = end_ns
                self.status = None

        return MockSpan()

    def test_export_llm_span_creates_record(self):
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        span = self._make_span(attributes={
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4",
            "gen_ai.prompt": "What is 2+2?",
            "gen_ai.completion": "4",
            "gen_ai.usage.prompt_tokens": 10,
            "gen_ai.usage.completion_tokens": 5,
        })

        from opentelemetry.sdk.trace.export import SpanExportResult
        result = exporter.export([span])
        assert result == SpanExportResult.SUCCESS

        time.sleep(0.1)
        records = load_records(limit=10)
        assert len(records) >= 1

    def test_export_sets_model(self):
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        span = self._make_span(attributes={
            "gen_ai.system": "anthropic",
            "gen_ai.request.model": "claude-sonnet-4-20250514",
        })
        exporter.export([span])
        time.sleep(0.1)

        records = load_records(limit=1)
        assert records[0]["step"]["model"] == "claude-sonnet-4-20250514"

    def test_export_calculates_latency(self):
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        span = self._make_span(attributes={
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4",
        }, duration_ms=250)
        exporter.export([span])
        time.sleep(0.1)

        records = load_records(limit=1)
        assert records[0]["step"]["latency_ms"] == 250

    def test_export_sets_tokens(self):
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        span = self._make_span(attributes={
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4",
            "gen_ai.usage.prompt_tokens": 42,
            "gen_ai.usage.completion_tokens": 18,
        })
        exporter.export([span])
        time.sleep(0.1)

        records = load_records(limit=1)
        assert records[0]["step"]["tokens_in"] == 42
        assert records[0]["step"]["tokens_out"] == 18

    def test_non_llm_span_ignored(self):
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        # Span without gen_ai attributes = not an LLM call
        span = self._make_span(attributes={
            "http.method": "GET",
            "http.url": "https://example.com",
        })
        exporter.export([span])
        time.sleep(0.1)

        records = load_records(limit=10)
        assert len(records) == 0

    def test_export_multiple_spans(self):
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        spans = [
            self._make_span(attributes={
                "gen_ai.system": "openai",
                "gen_ai.request.model": f"model-{i}",
            })
            for i in range(3)
        ]
        exporter.export(spans)
        time.sleep(0.2)

        records = load_records(limit=10)
        assert len(records) == 3

    def test_export_fail_open(self):
        """Exporter must not raise even with bad spans."""
        exporter = self._make_exporter()
        from opentelemetry.sdk.trace.export import SpanExportResult

        class BadSpan:
            name = "bad"
            attributes = None  # Will cause AttributeError
            start_time = None
            end_time = None

        result = exporter.export([BadSpan()])
        assert result == SpanExportResult.SUCCESS

    def test_export_with_fallback_keys(self):
        """Test that fallback attribute keys work."""
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        span = self._make_span(attributes={
            "gen_ai.system": "custom",
            "llm.request.model": "my-model",  # fallback key
            "llm.usage.prompt_tokens": 99,     # fallback key
        })
        exporter.export([span])
        time.sleep(0.1)

        records = load_records(limit=1)
        assert records[0]["step"]["model"] == "my-model"
        assert records[0]["step"]["tokens_in"] == 99

    def test_record_type_is_llm_call(self):
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        span = self._make_span(attributes={
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4",
        })
        exporter.export([span])
        time.sleep(0.1)

        records = load_records(limit=1)
        assert records[0]["step"]["type"] == "llm_call"

    def test_chain_links_across_exports(self):
        exporter = self._make_exporter()
        from atlast_ecp.storage import load_records

        for i in range(3):
            span = self._make_span(attributes={
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4",
                "gen_ai.prompt": f"prompt {i}",
            })
            exporter.export([span])
            time.sleep(0.01)  # Ensure distinct timestamps

        time.sleep(0.2)
        records = load_records(limit=10)
        sorted_r = sorted(records, key=lambda r: r["ts"])

        assert sorted_r[0]["chain"]["prev"] == "genesis"
        assert sorted_r[1]["chain"]["prev"] == sorted_r[0]["id"]
        assert sorted_r[2]["chain"]["prev"] == sorted_r[1]["id"]


# ─── init() Tests ────────────────────────────────────────────────────────────

class TestInit:
    def test_init_without_otel_returns_error(self, monkeypatch):
        """init() should gracefully handle missing OTel."""
        # If OTel IS installed, this test checks normal flow
        # If NOT installed, it checks the error handling
        from atlast_ecp.auto import init, reset
        reset()
        result = init()
        assert result["status"] in ("ok", "otel_not_installed", "error")
        assert "agent_did" in result

    def test_init_idempotent(self):
        """Calling init() twice returns already_initialized."""
        from atlast_ecp.auto import init, reset
        reset()
        r1 = init()
        r2 = init()
        if r1["status"] == "ok":
            assert r2["status"] == "already_initialized"

    def test_init_returns_did(self):
        from atlast_ecp.auto import init, reset
        reset()
        result = init()
        if result.get("agent_did"):
            assert result["agent_did"].startswith("did:ecp:")

    def test_init_importable_from_package(self):
        from atlast_ecp import init
        assert callable(init)
