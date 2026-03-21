"""
ECP Library Mode — wrap(client)
One line. Passive recording. Fail-Open.

Usage:
    from atlast_ecp import wrap
    from anthropic import Anthropic

    client = wrap(Anthropic())
    # Everything else stays the same.

Supported clients:
    - Anthropic (anthropic.Anthropic)
    - OpenAI (openai.OpenAI, openai.AzureOpenAI)
    - Google Gemini (google.generativeai.GenerativeModel)
    - LiteLLM (litellm module — patches litellm.completion)
"""

import time
from functools import wraps

from .core import record_async


def _wrap_anthropic(client):
    """Wrap an Anthropic client."""
    original_create = client.messages.create

    @wraps(original_create)
    def recorded_create(*args, **kwargs):
        in_content = kwargs.get("messages", args[0] if args else [])
        model = kwargs.get("model", "unknown")

        t_start = time.time()
        response = original_create(*args, **kwargs)
        latency_ms = int((time.time() - t_start) * 1000)

        # Extract response content
        out_content = ""
        tokens_in = tokens_out = None
        try:
            if hasattr(response, "content"):
                out_content = [
                    block.text for block in response.content
                    if hasattr(block, "text")
                ]
            if hasattr(response, "usage"):
                tokens_in = getattr(response.usage, "input_tokens", None)
                tokens_out = getattr(response.usage, "output_tokens", None)
        except Exception:
            pass

        record_async(
            input_content=in_content,
            output_content=out_content,
            step_type="llm_call",
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        return response

    client.messages.create = recorded_create
    return client


def _wrap_openai(client):
    """Wrap an OpenAI client."""
    original_create = client.chat.completions.create

    @wraps(original_create)
    def recorded_create(*args, **kwargs):
        in_content = kwargs.get("messages", [])
        model = kwargs.get("model", "unknown")

        t_start = time.time()
        response = original_create(*args, **kwargs)
        latency_ms = int((time.time() - t_start) * 1000)

        out_content = ""
        tokens_in = tokens_out = None
        try:
            if hasattr(response, "choices") and response.choices:
                out_content = response.choices[0].message.content or ""
            if hasattr(response, "usage"):
                tokens_in = getattr(response.usage, "prompt_tokens", None)
                tokens_out = getattr(response.usage, "completion_tokens", None)
        except Exception:
            pass

        record_async(
            input_content=in_content,
            output_content=out_content,
            step_type="llm_call",
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        return response

    client.chat.completions.create = recorded_create
    return client


def _wrap_gemini(client):
    """Wrap a Google Gemini GenerativeModel."""
    original_generate = client.generate_content

    @wraps(original_generate)
    def recorded_generate(*args, **kwargs):
        in_content = args[0] if args else kwargs.get("contents", "")
        model = getattr(client, "model_name", "gemini-unknown")

        t_start = time.time()
        response = original_generate(*args, **kwargs)
        latency_ms = int((time.time() - t_start) * 1000)

        out_content = ""
        tokens_in = tokens_out = None
        try:
            if hasattr(response, "text"):
                out_content = response.text
            if hasattr(response, "usage_metadata"):
                um = response.usage_metadata
                tokens_in = getattr(um, "prompt_token_count", None)
                tokens_out = getattr(um, "candidates_token_count", None)
        except Exception:
            pass

        record_async(
            input_content=in_content,
            output_content=out_content,
            step_type="llm_call",
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        return response

    client.generate_content = recorded_generate
    return client


def _wrap_litellm(module):
    """
    Wrap litellm module's completion() and acompletion() functions.
    Unlike other wrappers, this patches the module, not a client instance.
    Returns the module itself.
    """
    original_completion = module.completion

    @wraps(original_completion)
    def recorded_completion(*args, **kwargs):
        in_content = kwargs.get("messages", [])
        model = kwargs.get("model", args[0] if args else "unknown")

        t_start = time.time()
        response = original_completion(*args, **kwargs)
        latency_ms = int((time.time() - t_start) * 1000)

        out_content = ""
        tokens_in = tokens_out = None
        try:
            if hasattr(response, "choices") and response.choices:
                out_content = response.choices[0].message.content or ""
            if hasattr(response, "usage"):
                tokens_in = getattr(response.usage, "prompt_tokens", None)
                tokens_out = getattr(response.usage, "completion_tokens", None)
        except Exception:
            pass

        record_async(
            input_content=in_content,
            output_content=out_content,
            step_type="llm_call",
            model=str(model),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        return response

    module.completion = recorded_completion
    return module


def wrap(client):
    """
    Wrap any supported LLM client with ECP passive recording.

    Supports: Anthropic, OpenAI, AzureOpenAI, Google Gemini, LiteLLM.
    Auto-detects client type. Fail-Open: if wrapping fails, returns unchanged.

    Usage:
        client = wrap(Anthropic())       # Anthropic
        client = wrap(OpenAI())          # OpenAI
        client = wrap(model)             # Google Gemini GenerativeModel
        litellm = wrap(litellm)          # LiteLLM module

    Returns: wrapped client (same type, same interface, recording added)
    """
    try:
        class_name = type(client).__name__
        module_name = type(client).__module__

        # Anthropic
        if "anthropic" in module_name.lower() or class_name == "Anthropic":
            return _wrap_anthropic(client)

        # OpenAI / Azure
        if "openai" in module_name.lower() or class_name in ("OpenAI", "AzureOpenAI"):
            return _wrap_openai(client)

        # Google Gemini
        if "google" in module_name.lower() or class_name == "GenerativeModel":
            if hasattr(client, "generate_content"):
                return _wrap_gemini(client)

        # LiteLLM (module, not instance)
        if hasattr(client, "completion") and hasattr(client, "acompletion"):
            if getattr(client, "__name__", "") == "litellm":
                return _wrap_litellm(client)

        # Unknown client — return as-is (fail-open)
        return client

    except Exception:
        # Wrapping failed — return original client, Agent unaffected
        return client
