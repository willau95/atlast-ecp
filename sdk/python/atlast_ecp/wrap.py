"""
ECP Library Mode — wrap(client)
One line. Passive recording. Fail-Open.

Usage:
    from atlast_ecp import wrap
    from anthropic import Anthropic

    client = wrap(Anthropic())
    # Everything else stays the same.
    # Works with both regular and streaming calls.

Supported clients:
    - Anthropic (anthropic.Anthropic)
    - OpenAI (openai.OpenAI, openai.AzureOpenAI)
    - Google Gemini (google.generativeai.GenerativeModel)
    - LiteLLM (litellm module — patches litellm.completion)

Streaming support:
    All wrappers transparently handle stream=True.
    The stream is passed through chunk-by-chunk to the user unchanged.
    After the stream ends, the full response is recorded in a background thread.
    Zero latency impact — user receives chunks at exactly the same speed.
"""

import time
from typing import Optional
from functools import wraps

from .core import record_async


# ─── Streaming Wrappers ──────────────────────────────────────────────────────

class _RecordedStream:
    """
    Wraps a streaming response iterator. Passes chunks through transparently,
    then records the full aggregated response after stream ends.

    Supports: iteration, context manager, and common stream attributes.
    Fail-Open: if recording fails, the stream still works perfectly.
    """

    def __init__(self, stream, *, record_fn, in_content, model, t_start, provider,
                 session_id=None):
        self._stream = stream
        self._record_fn = record_fn
        self._in_content = in_content
        self._model = model
        self._t_start = t_start
        self._provider = provider
        self._session_id = session_id
        self._chunks = []
        self._recorded = False

    def __iter__(self):
        try:
            for chunk in self._stream:
                self._chunks.append(chunk)
                yield chunk
        finally:
            self._finalize()

    def __next__(self):
        try:
            chunk = next(self._stream)
            self._chunks.append(chunk)
            return chunk
        except StopIteration:
            self._finalize()
            raise

    def __enter__(self):
        if hasattr(self._stream, '__enter__'):
            self._stream.__enter__()
        return self

    def __exit__(self, *args):
        if hasattr(self._stream, '__exit__'):
            self._stream.__exit__(*args)
        self._finalize()

    def __getattr__(self, name):
        """Proxy all unknown attributes to the underlying stream."""
        return getattr(self._stream, name)

    def _finalize(self):
        """Record the complete response after stream ends. Called once. Fail-Open."""
        if self._recorded:
            return
        self._recorded = True

        try:
            latency_ms = int((time.time() - self._t_start) * 1000)

            try:
                out_content, tokens_in, tokens_out = self._extract_response()
            except Exception:
                out_content = f"[streamed {len(self._chunks)} chunks]"
                tokens_in = tokens_out = None

            self._record_fn(
                input_content=self._in_content,
                output_content=out_content,
                step_type="llm_call",
                model=self._model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                session_id=self._session_id,
            )
        except Exception:
            pass  # Fail-Open: recording failure NEVER affects the stream

    def _extract_response(self):
        """Extract full text + token counts from collected chunks."""
        if self._provider == "anthropic":
            return self._extract_anthropic()
        elif self._provider == "openai":
            return self._extract_openai()
        elif self._provider == "gemini":
            return self._extract_gemini()
        else:
            return f"[streamed {len(self._chunks)} chunks]", None, None

    def _extract_anthropic(self):
        """
        Anthropic streaming events:
        - message_start: contains usage.input_tokens
        - content_block_delta: contains delta.text
        - message_delta: contains usage.output_tokens
        """
        text_parts = []
        tokens_in = tokens_out = None

        for chunk in self._chunks:
            # content_block_delta
            if hasattr(chunk, 'delta') and hasattr(chunk.delta, 'text'):
                text_parts.append(chunk.delta.text)
            # message_start → input tokens
            if hasattr(chunk, 'message') and hasattr(chunk.message, 'usage'):
                t = getattr(chunk.message.usage, 'input_tokens', None)
                if t is not None:
                    tokens_in = t
            # message_delta → output tokens
            if hasattr(chunk, 'usage') and hasattr(chunk.usage, 'output_tokens'):
                t = getattr(chunk.usage, 'output_tokens', None)
                if t is not None:
                    tokens_out = t

        return "".join(text_parts), tokens_in, tokens_out

    def _extract_openai(self):
        """
        OpenAI streaming chunks:
        - chunk.choices[0].delta.content for text
        - Final chunk may have usage stats
        """
        text_parts = []
        tokens_in = tokens_out = None

        for chunk in self._chunks:
            try:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        text_parts.append(delta.content)
                # Some providers include usage in the last chunk
                if hasattr(chunk, 'usage') and chunk.usage:
                    tokens_in = getattr(chunk.usage, 'prompt_tokens', tokens_in)
                    tokens_out = getattr(chunk.usage, 'completion_tokens', tokens_out)
            except Exception:
                pass

        return "".join(text_parts), tokens_in, tokens_out

    def _extract_gemini(self):
        """Gemini streaming: each chunk has .text and possibly .usage_metadata."""
        text_parts = []
        tokens_in = tokens_out = None

        for chunk in self._chunks:
            try:
                if hasattr(chunk, 'text'):
                    text_parts.append(chunk.text)
                if hasattr(chunk, 'usage_metadata'):
                    um = chunk.usage_metadata
                    tokens_in = getattr(um, 'prompt_token_count', tokens_in)
                    tokens_out = getattr(um, 'candidates_token_count', tokens_out)
            except Exception:
                pass

        return "".join(text_parts), tokens_in, tokens_out


def _is_streaming(kwargs):
    """Check if the call requests streaming."""
    return kwargs.get("stream", False)


# ─── Client Wrappers ─────────────────────────────────────────────────────────

def _wrap_anthropic(client, session_id=None):
    """Wrap an Anthropic client (regular + streaming)."""
    original_create = client.messages.create

    @wraps(original_create)
    def recorded_create(*args, **kwargs):
        in_content = kwargs.get("messages", args[0] if args else [])
        model = kwargs.get("model", "unknown")
        streaming = _is_streaming(kwargs)

        t_start = time.time()
        response = original_create(*args, **kwargs)

        if streaming:
            # Return a transparent stream wrapper
            return _RecordedStream(
                response,
                record_fn=record_async,
                in_content=in_content,
                model=model,
                t_start=t_start,
                provider="anthropic",
                session_id=session_id,
            )

        # Non-streaming: record immediately
        latency_ms = int((time.time() - t_start) * 1000)

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
            session_id=session_id,
        )
        return response

    client.messages.create = recorded_create

    # Also wrap messages.stream() if it exists (Anthropic's context manager API)
    if hasattr(client.messages, 'stream'):
        original_stream = client.messages.stream

        @wraps(original_stream)
        def recorded_stream(*args, **kwargs):
            in_content = kwargs.get("messages", args[0] if args else [])
            model = kwargs.get("model", "unknown")
            t_start = time.time()
            stream_ctx = original_stream(*args, **kwargs)
            return _RecordedStream(
                stream_ctx,
                record_fn=record_async,
                in_content=in_content,
                model=model,
                t_start=t_start,
                provider="anthropic",
                session_id=session_id,
            )

        client.messages.stream = recorded_stream

    client._ecp_wrapped = True
    return client


def _wrap_openai(client, session_id=None):
    """Wrap an OpenAI client (regular + streaming)."""
    original_create = client.chat.completions.create

    @wraps(original_create)
    def recorded_create(*args, **kwargs):
        in_content = kwargs.get("messages", [])
        model = kwargs.get("model", "unknown")
        streaming = _is_streaming(kwargs)

        t_start = time.time()
        response = original_create(*args, **kwargs)

        if streaming:
            return _RecordedStream(
                response,
                record_fn=record_async,
                in_content=in_content,
                model=model,
                t_start=t_start,
                provider="openai",
                session_id=session_id,
            )

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
            session_id=session_id,
        )
        return response

    client.chat.completions.create = recorded_create
    client._ecp_wrapped = True
    return client


def _wrap_gemini(client, session_id=None):
    """Wrap a Google Gemini GenerativeModel (regular + streaming)."""
    original_generate = client.generate_content

    @wraps(original_generate)
    def recorded_generate(*args, **kwargs):
        in_content = args[0] if args else kwargs.get("contents", "")
        model = getattr(client, "model_name", "gemini-unknown")
        streaming = kwargs.get("stream", False)

        t_start = time.time()
        response = original_generate(*args, **kwargs)

        if streaming:
            return _RecordedStream(
                response,
                record_fn=record_async,
                in_content=in_content,
                model=model,
                t_start=t_start,
                provider="gemini",
                session_id=session_id,
            )

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
            session_id=session_id,
        )
        return response

    client.generate_content = recorded_generate
    client._ecp_wrapped = True
    return client


def _wrap_litellm(module, session_id=None):
    """
    Wrap litellm module's completion() function (regular + streaming).
    Unlike other wrappers, this patches the module, not a client instance.
    Returns the module itself.
    """
    original_completion = module.completion

    @wraps(original_completion)
    def recorded_completion(*args, **kwargs):
        in_content = kwargs.get("messages", [])
        model = kwargs.get("model", args[0] if args else "unknown")
        streaming = _is_streaming(kwargs)

        t_start = time.time()
        response = original_completion(*args, **kwargs)

        if streaming:
            return _RecordedStream(
                response,
                record_fn=record_async,
                in_content=in_content,
                model=str(model),
                t_start=t_start,
                provider="openai",  # LiteLLM uses OpenAI-compatible format
                session_id=session_id,
            )

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
            session_id=session_id,
        )
        return response

    module.completion = recorded_completion
    return module


# ─── Public API ───────────────────────────────────────────────────────────────

def wrap(client, session_id: Optional[str] = None):
    """
    Wrap any supported LLM client with ECP passive recording.

    Supports: Anthropic, OpenAI, AzureOpenAI, Google Gemini, LiteLLM.
    Auto-detects client type. Handles both regular and streaming calls.
    Fail-Open: if wrapping fails, returns unchanged client.

    Usage:
        client = wrap(Anthropic())       # Anthropic
        client = wrap(OpenAI())          # OpenAI
        client = wrap(model)             # Google Gemini GenerativeModel
        litellm = wrap(litellm)          # LiteLLM module

    Streaming works transparently:
        stream = client.chat.completions.create(messages=[...], stream=True)
        for chunk in stream:
            print(chunk)  # No change — chunks arrive at same speed
        # After stream ends, ECP record is created in background

    Returns: wrapped client (same type, same interface, recording added)
    """
    # Prevent double-wrapping
    if getattr(client, '_ecp_wrapped', False) is True:
        return client
    try:
        class_name = type(client).__name__
        module_name = type(client).__module__

        # Anthropic
        if "anthropic" in module_name.lower() or class_name == "Anthropic":
            return _wrap_anthropic(client, session_id=session_id)

        # OpenAI / Azure
        if "openai" in module_name.lower() or class_name in ("OpenAI", "AzureOpenAI"):
            return _wrap_openai(client, session_id=session_id)

        # Google Gemini
        if "google" in module_name.lower() or class_name == "GenerativeModel":
            if hasattr(client, "generate_content"):
                return _wrap_gemini(client, session_id=session_id)

        # LiteLLM (module, not instance)
        if hasattr(client, "completion") and hasattr(client, "acompletion"):
            if getattr(client, "__name__", "") == "litellm":
                return _wrap_litellm(client, session_id=session_id)

        # Unknown client — return as-is (fail-open)
        return client

    except Exception:
        # Wrapping failed — return original client, Agent unaffected
        return client
