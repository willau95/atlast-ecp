"""
ECP Auto-Instrumentation — one line to record all LLM calls.

Usage:
    from atlast_ecp import init
    init()
    # All LLM calls are now recorded as ECP evidence.
    # Works with: OpenAI, Anthropic, Gemini, Cohere, Mistral,
    # Bedrock, Together, Ollama, LangChain, LlamaIndex, CrewAI.

How it works:
    1. Sets up an OpenTelemetry TracerProvider with ECPSpanExporter
    2. Auto-detects installed LLM libraries
    3. Instruments each one via OpenLLMetry instrumentors
    4. Every LLM call → OTel Span → ECPSpanExporter → core.record() → .ecp/

Fail-Open: if any step fails, LLM calls are unaffected.
"""

import warnings
import threading
from typing import Any, Optional

_initialized = False
_init_lock = threading.Lock()

# Map of library name → OpenLLMetry instrumentor class path
_INSTRUMENTORS = {
    "openai": "opentelemetry.instrumentation.openai.OpenAIInstrumentor",
    "anthropic": "opentelemetry.instrumentation.anthropic.AnthropicInstrumentor",
    "google_generativeai": "opentelemetry.instrumentation.google_generativeai.GoogleGenerativeAiInstrumentor",
    "cohere": "opentelemetry.instrumentation.cohere.CohereInstrumentor",
    "mistralai": "opentelemetry.instrumentation.mistralai.MistralAiInstrumentor",
    "bedrock": "opentelemetry.instrumentation.bedrock.BedrockInstrumentor",
    "together": "opentelemetry.instrumentation.together.TogetherAiInstrumentor",
    "ollama": "opentelemetry.instrumentation.ollama.OllamaInstrumentor",
    "langchain": "opentelemetry.instrumentation.langchain.LangchainInstrumentor",
    "llama_index": "opentelemetry.instrumentation.llamaindex.LlamaindexInstrumentor",
    "crewai": "opentelemetry.instrumentation.crewai.CrewAIInstrumentor",
}


def init(agent_id: Optional[str] = None, agent_name: Optional[str] = None, ecp_dir: Optional[str] = None) -> dict:
    """
    Initialize ECP auto-instrumentation.

    One call instruments all installed LLM libraries.
    Safe to call multiple times (idempotent).

    Args:
        agent_id: Optional agent identifier (uses DID if not provided)

    Returns:
        dict with initialization status:
        {
            "status": "ok",
            "agent_did": "did:ecp:...",
            "instrumented": ["openai", "anthropic"],
            "skipped": ["cohere", "mistralai"],
        }
    """
    global _initialized

    warnings.warn(
        "atlast_ecp.auto (init) is experimental and may change in future versions.",
        FutureWarning, stacklevel=2,
    )

    with _init_lock:
        if _initialized:
            from .core import get_identity
            return {
                "status": "already_initialized",
                "agent_did": get_identity()["did"],
            }

        # Resolve alias
        agent_id = agent_id or agent_name

        result: dict[str, Any] = {
            "status": "ok",
            "agent_did": None,
            "instrumented": [],
            "skipped": [],
            "errors": [],
        }

        try:
            # Get agent identity
            from .core import get_identity
            identity = get_identity()
            result["agent_did"] = identity["did"]

            # Set up OTel TracerProvider + ECPSpanExporter
            _setup_otel()

            # Instrument all detected libraries
            for lib_name, instrumentor_path in _INSTRUMENTORS.items():
                status = _try_instrument(lib_name, instrumentor_path)
                if status == "ok":
                    result["instrumented"].append(lib_name)
                elif status == "not_installed":
                    result["skipped"].append(lib_name)
                else:
                    result["errors"].append(f"{lib_name}: {status}")

            _initialized = True

        except ImportError:
            result["status"] = "otel_not_installed"
            result["errors"].append(
                "opentelemetry-sdk not installed. Run: pip install atlast-ecp[otel]"
            )
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(str(e))

        return result


def _setup_otel():
    """Configure OTel TracerProvider with ECPSpanExporter."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from .otel_exporter import ECPSpanExporter

    # Only set up if no provider is configured yet
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        # Already has a provider — just add our exporter
        current.add_span_processor(SimpleSpanProcessor(ECPSpanExporter()))
    else:
        # Set up new provider
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(ECPSpanExporter()))
        trace.set_tracer_provider(provider)


def _try_instrument(lib_name: str, instrumentor_path: str) -> str:
    """
    Try to instrument a library. Returns status string.

    Returns:
        "ok"            - instrumented successfully
        "not_installed" - library not installed (skip)
        "error: ..."    - instrumentation failed
    """
    # Check if the library is installed
    try:
        __import__(lib_name)
    except ImportError:
        return "not_installed"

    # Try to load and run the instrumentor
    try:
        module_path, class_name = instrumentor_path.rsplit(".", 1)
        mod = __import__(module_path, fromlist=[class_name])
        instrumentor_cls = getattr(mod, class_name)
        instrumentor = instrumentor_cls()

        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument()

        return "ok"
    except ImportError:
        # Instrumentor package not installed
        return "not_installed"
    except Exception as e:
        return f"error: {e}"


def reset():
    """Reset initialization state (for testing)."""
    global _initialized
    _initialized = False
