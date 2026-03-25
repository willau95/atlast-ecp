"""
ECP OTel Exporter — converts OpenTelemetry spans to ECP records.

This is the bridge between OpenLLMetry (OTel-based LLM instrumentation)
and ECP's evidence chain. Every LLM span becomes an ECP record.

Usage:
    from atlast_ecp import init
    init()  # Sets up OTel + ECPSpanExporter automatically

Architecture:
    OTel Instrumentor → OTel Span → ECPSpanExporter → core.record() → .ecp/
"""


import warnings
from typing import Sequence

_WARNED = False

try:
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
    from opentelemetry.trace import StatusCode
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


# Gen AI semantic convention attribute keys (OpenLLMetry standard)
_ATTR_SYSTEM = "gen_ai.system"
_ATTR_MODEL = "gen_ai.request.model"
_ATTR_PROMPT_TOKENS = "gen_ai.usage.prompt_tokens"
_ATTR_COMPLETION_TOKENS = "gen_ai.usage.completion_tokens"
_ATTR_PROMPT = "gen_ai.prompt"
_ATTR_COMPLETION = "gen_ai.completion"

# Fallback keys used by some instrumentors
_FALLBACK_MODEL_KEYS = [
    "llm.request.model", "llm.model", "model",
    "gen_ai.request.model",
]
_FALLBACK_PROMPT_TOKEN_KEYS = [
    "llm.usage.prompt_tokens", "gen_ai.usage.prompt_tokens",
    "llm.token_count.prompt",
]
_FALLBACK_COMPLETION_TOKEN_KEYS = [
    "llm.usage.completion_tokens", "gen_ai.usage.completion_tokens",
    "llm.token_count.completion",
]


def _get_attr(attributes: dict, primary: str, fallbacks: list | None = None):
    """Get attribute with fallback keys."""
    val = attributes.get(primary)
    if val is not None:
        return val
    for key in (fallbacks or []):
        val = attributes.get(key)
        if val is not None:
            return val
    return None


if HAS_OTEL:
    class ECPSpanExporter(SpanExporter):
        """
        OTel SpanExporter that converts LLM spans to ECP records.
        Only processes spans with gen_ai.* attributes (LLM calls).
        Non-LLM spans are silently ignored.
        """

        def __init__(self):
            global _WARNED
            if not _WARNED:
                warnings.warn(
                    "atlast_ecp.otel_exporter is experimental and may change in future versions.",
                    FutureWarning, stacklevel=2,
                )
                _WARNED = True
            from .core import record as _record
            self._record = _record

        def export(self, spans: Sequence) -> "SpanExportResult":
            for span in spans:
                try:
                    self._process_span(span)
                except Exception:
                    pass  # Fail-Open
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            pass

        def force_flush(self, timeout_millis: int = 0) -> bool:
            return True

        def _process_span(self, span) -> None:
            attrs = dict(span.attributes) if span.attributes else {}

            # Only process LLM spans (must have gen_ai or llm attributes)
            model = _get_attr(attrs, _ATTR_MODEL, _FALLBACK_MODEL_KEYS)
            if not model and _ATTR_SYSTEM not in attrs:
                return  # Not an LLM span

            # Extract input/output content for hashing
            input_content = attrs.get(_ATTR_PROMPT, span.name or "")
            output_content = attrs.get(_ATTR_COMPLETION, "")

            # Extract tokens
            tokens_in = _get_attr(attrs, _ATTR_PROMPT_TOKENS, _FALLBACK_PROMPT_TOKEN_KEYS)
            tokens_out = _get_attr(attrs, _ATTR_COMPLETION_TOKENS, _FALLBACK_COMPLETION_TOKEN_KEYS)

            # Compute latency from span timestamps (nanoseconds → ms)
            latency_ms = 0
            if span.start_time and span.end_time:
                latency_ms = int((span.end_time - span.start_time) / 1_000_000)

            # Convert to int if present
            if tokens_in is not None:
                tokens_in = int(tokens_in)
            if tokens_out is not None:
                tokens_out = int(tokens_out)

            self._record(
                input_content=input_content,
                output_content=output_content,
                step_type="llm_call",
                model=str(model) if model else None,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
