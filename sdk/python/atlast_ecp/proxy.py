"""
ATLAST Proxy — transparent HTTP reverse proxy for zero-code ECP recording.

Intercepts LLM API calls, records SHA-256 hashes locally, forwards everything
unchanged. Supports streaming (SSE). Fail-Open: proxy errors never break the agent.

Usage:
    atlast proxy --port 8340
    OPENAI_BASE_URL=http://localhost:8340 python my_agent.py

    # Or all-in-one:
    atlast run python my_agent.py

Supported providers (auto-detected from request path):
    - OpenAI-compatible: OpenAI, Qwen, Kimi, DeepSeek, Yi, Groq, Together
    - Anthropic: /v1/messages
    - Google Gemini: /v1beta/models/*/generateContent
    - MiniMax: /v1/text/chatcompletion*

Architecture:
    Agent → localhost:PORT (ATLAST Proxy) → Real API
                  ↓
           ~/.ecp/records/ (local ECP records, only hashes)
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

# aiohttp is optional dependency
try:
    from aiohttp import web, ClientSession, TCPConnector
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ─── Provider Detection ───────────────────────────────────────────────────────

# Map of path patterns → provider name (format-based, not vendor-locked)
# Any API that uses the same path format is automatically supported.
PROVIDER_ROUTES = {
    # OpenAI-compatible format (covers: OpenAI, Ollama, Groq, Together, Qwen,
    # Kimi, DeepSeek, Yi, Mistral, Azure OpenAI, LM Studio, vLLM, LocalAI,
    # and any other service using the OpenAI API format)
    "/v1/chat/completions": "openai",
    "/v1/completions": "openai",
    "/v1/embeddings": "openai",
    # Anthropic format
    "/v1/messages": "anthropic",
    # MiniMax format
    "/v1/text/chatcompletion": "minimax",
    # Ollama native format (non-OpenAI mode)
    "/api/chat": "ollama",
    "/api/generate": "ollama",
    # Azure OpenAI format
    "/openai/deployments": "openai",
}


def _detect_provider(path: str) -> str:
    """Detect API provider from request path.

    Format-based detection: any service using the same API format
    is automatically supported without code changes.
    """
    for pattern, provider in PROVIDER_ROUTES.items():
        if path.startswith(pattern):
            return provider
    if "/v1beta/models/" in path and "generateContent" in path:
        return "gemini"
    # Fallback: if path contains known keywords, make a best guess
    if "chat" in path or "completions" in path or "messages" in path:
        return "openai"  # Assume OpenAI-compatible format
    return "unknown"


def _detect_action(path: str) -> str:
    """Map request path to ECP action type."""
    if "chat" in path or "completions" in path or "messages" in path or "generateContent" in path or "generate" in path:
        return "llm_call"
    if "embeddings" in path:
        return "tool_call"
    return "llm_call"


# ─── Upstream Resolution ──────────────────────────────────────────────────────

# Default upstream URLs per provider
DEFAULT_UPSTREAMS = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "minimax": "https://api.minimax.chat",
    "ollama": "http://127.0.0.1:11434",
    # Local model servers (auto-detected)
    "lmstudio": "http://127.0.0.1:1234",
    "vllm": "http://127.0.0.1:8000",
    "localai": "http://127.0.0.1:8080",
}

# Additional trusted API domains that can be used via X-Real-API-URL header
TRUSTED_API_DOMAINS = {
    # Cloud providers
    "openrouter.ai", "api.openrouter.ai",
    "api.together.xyz",
    "api.groq.com",
    "api.deepseek.com",
    "api.mistral.ai",
    "api.fireworks.ai",
    "api.perplexity.ai",
    "api.cohere.ai", "api.cohere.com",
    "generativelanguage.googleapis.com",
    "api.x.ai",
    # Local model servers (localhost variants)
    "localhost", "127.0.0.1",
    "localhost:11434", "127.0.0.1:11434",   # Ollama
    "localhost:1234", "127.0.0.1:1234",     # LM Studio
    "localhost:8000", "127.0.0.1:8000",     # vLLM / HuggingFace transformers serve
    "localhost:8080", "127.0.0.1:8080",     # LocalAI
    "localhost:5000", "127.0.0.1:5000",     # Custom local servers
    "localhost:3000", "127.0.0.1:3000",     # Custom local servers
}

# Env vars that might contain the original upstream URL
UPSTREAM_ENV_VARS = [
    "ATLAST_UPSTREAM_URL",       # Explicit override (any provider)
    "ATLAST_OPENAI_UPSTREAM",    # Per-provider overrides
    "ATLAST_ANTHROPIC_UPSTREAM",
    "ATLAST_OLLAMA_UPSTREAM",
    "OPENAI_API_BASE",           # Legacy OpenAI
    "OPENAI_BASE_URL_ORIGINAL",  # Saved by atlast run
    "ANTHROPIC_BASE_URL_ORIGINAL",
    "OLLAMA_HOST",               # Ollama custom host
    "VLLM_BASE_URL",             # vLLM custom host
    "LMSTUDIO_BASE_URL",         # LM Studio custom host
]


def _resolve_upstream(request_headers: dict, provider: str) -> str:
    """Determine the real upstream API URL."""
    # 0. Auto-detect by API key prefix (OpenRouter, Together, Groq, etc.)
    auth = request_headers.get("Authorization") or request_headers.get("authorization") or ""
    api_key = request_headers.get("x-api-key") or request_headers.get("X-Api-Key") or ""
    bearer = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else ""
    key = bearer or api_key
    if key.startswith("sk-or-"):
        return "https://openrouter.ai/api"
    if key.startswith("gsk_"):
        return "https://api.groq.com/openai"
    if key.startswith("xai-"):
        return "https://api.x.ai"

    # 1. Explicit header override (validated against known domains)
    explicit = request_headers.get("X-Real-API-URL") or request_headers.get("x-real-api-url")
    if explicit:
        from urllib.parse import urlparse
        allowed_domains = set(urlparse(u).netloc for u in DEFAULT_UPSTREAMS.values())
        allowed_domains.update(TRUSTED_API_DOMAINS)
        # Also allow env-configured upstreams
        for var in UPSTREAM_ENV_VARS:
            val = os.environ.get(var)
            if val:
                allowed_domains.add(urlparse(val).netloc)
        parsed = urlparse(explicit)
        hostname = parsed.hostname or ""
        is_local = hostname in ("localhost", "127.0.0.1")
        # Block dangerous addresses (SSRF prevention)
        if hostname and (
            hostname.startswith("169.254.") or  # Link-local / cloud metadata
            hostname == "0.0.0.0" or            # Wildcard bind
            hostname == "::1" or hostname.startswith("::ffff:") or  # IPv6 loopback
            hostname.startswith("10.") or       # RFC1918
            hostname.startswith("172.") or      # RFC1918 (simplified)
            hostname.startswith("192.168.") or  # RFC1918
            hostname.startswith("fc") or hostname.startswith("fd")  # IPv6 ULA
        ):
            is_local = False
        if is_local or parsed.netloc in allowed_domains:
            return explicit.rstrip("/")
        else:
            try:
                import structlog
                structlog.get_logger().warning("proxy_blocked_upstream", url=explicit, allowed=list(allowed_domains))
            except ImportError:
                import logging
                logging.getLogger(__name__).warning("proxy_blocked_upstream url=%s allowed=%s", explicit, list(allowed_domains))
            # Fall through to env/default instead of using untrusted URL

    # 2. Env vars
    for var in UPSTREAM_ENV_VARS:
        val = os.environ.get(var)
        if val:
            return val.rstrip("/")

    # 3. Default per provider
    return DEFAULT_UPSTREAMS.get(provider, "https://api.openai.com")


# ─── Response Parsing ─────────────────────────────────────────────────────────

def _extract_model_from_request(body: bytes) -> str:
    """Extract model name from request body."""
    try:
        data = json.loads(body)
        return data.get("model", "unknown")
    except Exception:
        return "unknown"


def _extract_tokens_from_response(body: bytes, provider: str) -> tuple:
    """Extract token counts from response body. Returns (tokens_in, tokens_out).
    Handles: OpenAI, Anthropic, Ollama, Google Gemini, and generic formats.
    """
    try:
        data = json.loads(body)
        usage = data.get("usage", {})

        # 1. Standard usage object (OpenAI, most providers)
        tin = usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("prompt_eval_count")
        tout = usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("eval_count")

        # 2. Ollama top-level fields (not in usage object)
        if not tin:
            tin = data.get("prompt_eval_count")
        if not tout:
            tout = data.get("eval_count")

        # 3. Google Gemini format (usageMetadata)
        if not tin and "usageMetadata" in data:
            meta = data["usageMetadata"]
            tin = meta.get("promptTokenCount")
            tout = meta.get("candidatesTokenCount") or meta.get("totalTokenCount")

        # 4. Nested in choices (some providers)
        if not tin and "choices" in data:
            for choice in data.get("choices", []):
                u = choice.get("usage", {})
                if u:
                    tin = tin or u.get("prompt_tokens") or u.get("input_tokens")
                    tout = tout or u.get("completion_tokens") or u.get("output_tokens")

        return tin, tout
    except Exception:
        return None, None


def _reconstruct_sse_content(chunks: bytes, provider: str) -> dict:
    """
    Reconstruct full response content from SSE stream chunks.

    Returns dict with:
      - content: str — assembled text content
      - stop_reason: str|None — "end_turn", "tool_use", "stop", "tool_calls", etc.
      - tool_calls: list[dict] — extracted tool call names and inputs
      - is_error: bool — whether the response is a provider error
    """
    result = {"content": "", "stop_reason": None, "tool_calls": [], "is_error": False,
              "tokens_in": None, "tokens_out": None}
    try:
        text = chunks.decode("utf-8", errors="replace")
        content_parts = []
        tool_calls_map: dict[int, dict] = {}  # index → {name, input_json_parts}
        tool_calls_anthropic: list[dict] = []
        current_tool_block: Optional[dict] = None

        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                continue
            try:
                data = json.loads(data_str)

                # Check for error responses
                if data.get("type") == "error" or data.get("error"):
                    result["is_error"] = True
                    error_msg = data.get("error", {})
                    if isinstance(error_msg, dict):
                        content_parts.append(json.dumps(data, ensure_ascii=False))
                    continue

                # Extract usage from any SSE chunk (OpenAI sends in final chunk)
                usage = data.get("usage", {})
                if usage:
                    result["tokens_in"] = result["tokens_in"] or usage.get("prompt_tokens") or usage.get("input_tokens")
                    result["tokens_out"] = result["tokens_out"] or usage.get("completion_tokens") or usage.get("output_tokens")

                if provider in ("openai", "minimax"):
                    for choice in data.get("choices", []):
                        delta = choice.get("delta", {})
                        # Text content
                        if "content" in delta and delta["content"]:
                            content_parts.append(delta["content"])
                        # Tool calls (OpenAI format)
                        if "tool_calls" in delta:
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_map:
                                    tool_calls_map[idx] = {"name": "", "input_parts": []}
                                if tc.get("function", {}).get("name"):
                                    tool_calls_map[idx]["name"] = tc["function"]["name"]
                                if tc.get("function", {}).get("arguments"):
                                    tool_calls_map[idx]["input_parts"].append(tc["function"]["arguments"])
                        # Stop reason
                        fr = choice.get("finish_reason")
                        if fr:
                            result["stop_reason"] = fr

                elif provider == "anthropic":
                    msg_type = data.get("type", "")
                    # Content block start (text or tool_use)
                    if msg_type == "content_block_start":
                        cb = data.get("content_block", {})
                        if cb.get("type") == "tool_use":
                            current_tool_block = {"name": cb.get("name", ""), "input_parts": []}
                        else:
                            current_tool_block = None
                    # Content delta
                    elif msg_type == "content_block_delta":
                        delta = data.get("delta", {})
                        # Support both formats: {type:"text_delta", text:"..."} and {text:"..."}
                        delta_type = delta.get("type", "")
                        if delta.get("text") and delta_type in ("text_delta", ""):
                            content_parts.append(delta["text"])
                        elif delta_type == "input_json_delta" and current_tool_block is not None:
                            current_tool_block["input_parts"].append(delta.get("partial_json", ""))
                    # Content block stop
                    elif msg_type == "content_block_stop":
                        if current_tool_block is not None:
                            tool_calls_anthropic.append(current_tool_block)
                            current_tool_block = None
                    # Message delta (stop reason + usage)
                    elif msg_type == "message_delta":
                        sr = data.get("delta", {}).get("stop_reason")
                        if sr:
                            result["stop_reason"] = sr
                        # Anthropic sends output token count in message_delta.usage
                        u = data.get("usage", {})
                        if u.get("output_tokens"):
                            result["tokens_out"] = u["output_tokens"]
                    # Message start (has input token count)
                    elif msg_type == "message_start":
                        msg = data.get("message", {})
                        u = msg.get("usage", {})
                        if u.get("input_tokens"):
                            result["tokens_in"] = u["input_tokens"]

            except json.JSONDecodeError:
                continue

        result["content"] = "".join(content_parts)

        # Assemble tool calls
        if tool_calls_map:
            for idx in sorted(tool_calls_map.keys()):
                tc = tool_calls_map[idx]
                input_str = "".join(tc["input_parts"])
                try:
                    input_parsed = json.loads(input_str) if input_str else {}
                except json.JSONDecodeError:
                    input_parsed = input_str
                result["tool_calls"].append({"name": tc["name"], "input": input_parsed})
        if tool_calls_anthropic:
            for tc in tool_calls_anthropic:
                input_str = "".join(tc["input_parts"])
                try:
                    input_parsed = json.loads(input_str) if input_str else {}
                except json.JSONDecodeError:
                    input_parsed = input_str
                result["tool_calls"].append({"name": tc["name"], "input": input_parsed})

        return result
    except Exception:
        result["content"] = chunks.decode("utf-8", errors="replace")
        return result


# ─── Message Extraction (Vault v2) ────────────────────────────────────────────

# Session tracking for system prompt deduplication
# Capped at 1000 entries to prevent unbounded memory growth
_SESSION_CACHE_MAX = 1000
_session_system_prompts: dict[str, str] = {}  # session_id → last system_prompt_hash
_session_lock = threading.Lock()

# ─── Conversation Buffer ─────────────────────────────────────────────────────
# Aggregates multiple API calls (user→tool_call→tool_result→...→final) into
# one complete ECP record. Key = session_id.

_conversation_buffers: dict[str, dict] = {}  # session_id → buffer
_conv_lock = threading.Lock()
_CONV_TIMEOUT_S = 300  # Flush orphaned buffers after 5 minutes
_CONV_MAX_BUFFERS = 100  # Cap to prevent unbounded memory growth


def _flush_conversation(session_id: str):
    """Flush a conversation buffer into a single aggregated ECP record."""
    with _conv_lock:
        buf = _conversation_buffers.pop(session_id, None)
    if not buf or not buf.get("steps"):
        return

    steps = buf["steps"]
    first = steps[0]
    last = steps[-1]

    # Aggregate: user input from first step, final output from last
    user_input = first.get("input", "")
    final_output = last.get("output", "")

    # Collect all tool calls across all steps
    all_tool_calls = []
    for s in steps:
        if s.get("tool_calls"):
            all_tool_calls.extend(s["tool_calls"])

    # Build detailed steps log for vault
    steps_detail = []
    for i, s in enumerate(steps):
        step_info = {
            "step": i + 1,
            "latency_ms": s.get("latency_ms", 0),
            "has_tool_calls": bool(s.get("tool_calls")),
        }
        if s.get("tool_calls"):
            step_info["tool_calls"] = [
                {"name": tc.get("name", ""), "input": tc.get("input", {})}
                for tc in s["tool_calls"]
            ]
        if s.get("output") and not s["output"].startswith('{"tool_calls"'):
            step_info["output_preview"] = s["output"][:200]
        steps_detail.append(step_info)

    # Total latency and tokens
    total_latency = sum(s.get("latency_ms", 0) for s in steps)
    total_tokens_in = sum(s.get("tokens_in", 0) or 0 for s in steps)
    total_tokens_out = sum(s.get("tokens_out", 0) or 0 for s in steps)

    # Build flags for the aggregated record (no tool_continuation/empty flags)
    agg_flags = []
    if any(s.get("is_streaming") for s in steps):
        agg_flags.append("streaming")
    if all_tool_calls:
        agg_flags.append("has_tool_calls")
    if any(s.get("is_infra") for s in steps):
        agg_flags.append("infra_error")
    if any(s.get("is_provider_error") for s in steps):
        agg_flags.append("provider_error")
    # Detect behavioral flags from final output
    from .signals import detect_flags
    behavioral = detect_flags(
        final_output,
        latency_ms=total_latency,
    )
    for f in behavioral:
        if f not in agg_flags:
            agg_flags.append(f)

    # Build vault output with full conversation detail
    vault_output = final_output
    if all_tool_calls:
        vault_output = json.dumps({
            "final_response": final_output,
            "tool_calls_used": [{"name": tc.get("name", ""), "input": tc.get("input", {})} for tc in all_tool_calls],
            "steps": len(steps),
        }, ensure_ascii=False)

    vault_extra = {
        "vault_version": 2,
        "system_prompt": first.get("system_prompt"),
        "full_request_hash": first.get("full_request_hash"),
        "session_id": session_id,
        "conversation_steps": steps_detail,
        "total_api_calls": len(steps),
        "tool_calls_count": len(all_tool_calls),
    }

    try:
        from .core import record_minimal_v2
        record_minimal_v2(
            input_content=user_input,
            output_content=vault_output,
            agent=buf.get("agent", "proxy"),
            action="llm_call",
            model=first.get("model") or last.get("model"),
            latency_ms=total_latency,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            session_id=session_id,
            flags=list(set(agg_flags)) if agg_flags else None,
            vault_extra=vault_extra,
        )
    except Exception:
        pass  # Fail-Open


def _cleanup_stale_buffers():
    """Flush conversation buffers older than timeout. Caps total buffer count."""
    now = time.time()
    stale = []
    with _conv_lock:
        for sid, buf in _conversation_buffers.items():
            if now - buf.get("last_update", 0) > _CONV_TIMEOUT_S:
                stale.append(sid)
        # Hard cap: if too many buffers, flush oldest
        if len(_conversation_buffers) > _CONV_MAX_BUFFERS:
            by_age = sorted(_conversation_buffers.items(), key=lambda x: x[1].get("last_update", 0))
            for sid, _ in by_age[:len(_conversation_buffers) - _CONV_MAX_BUFFERS]:
                if sid not in stale:
                    stale.append(sid)
    for sid in stale:
        _flush_conversation(sid)


def _extract_new_content(req_body: bytes, provider: str) -> dict:
    """
    Extract only the NEW content from an API request, avoiding duplicate
    storage of conversation history.

    Returns a dict with:
      - input: last user message (the new instruction)
      - system_prompt: system prompt (only if first time or changed)
      - full_request_hash: SHA-256 of the complete request body (for audit verification)
      - context_messages_count: total messages in the request
      - session_id: derived from request content for grouping

    Architecture principle: store new content only, but hash EVERYTHING
    so auditors can verify completeness via chain reconstruction.
    """
    import hashlib

    req_text = req_body.decode("utf-8", errors="replace")
    full_request_hash = "sha256:" + hashlib.sha256(req_body).hexdigest()

    result = {
        "input": req_text,  # fallback: store full body if parsing fails
        "system_prompt": None,
        "full_request_hash": full_request_hash,
        "context_messages_count": 0,
        "session_id": None,
        "is_tool_continuation": False,
        "is_heartbeat": False,
    }

    try:
        data = json.loads(req_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return result

    messages = data.get("messages", [])
    if not messages:
        # Not a chat completion (might be embeddings, etc.) — store full body
        return result

    result["context_messages_count"] = len(messages)

    # Detect tool_continuation: last message is role=tool (OpenAI) or
    # role=user with content containing tool_result (Anthropic)
    last_msg = messages[-1] if messages else {}
    if last_msg.get("role") == "tool":
        result["is_tool_continuation"] = True
    elif last_msg.get("role") == "user":
        content = last_msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    result["is_tool_continuation"] = True
                    break

    # Extract system prompt
    system_parts = []
    for m in messages:
        if m.get("role") == "system":
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content
                )
            system_parts.append(content)

    system_prompt = "\n".join(system_parts) if system_parts else None

    # Extract the last user message (= the new instruction)
    last_user_content = None
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, list):
                # Handle multimodal: text parts only (images are not stored in vault)
                text_parts = []
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        text_parts.append(p.get("text", ""))
                    elif isinstance(p, str):
                        text_parts.append(p)
                content = "\n".join(text_parts)
            last_user_content = content
            break

    if last_user_content is not None:
        result["input"] = last_user_content

    # Derive a session_id from the system prompt + model for grouping
    model_name = data.get("model", "unknown")
    session_seed = (system_prompt or "") + ":" + model_name
    session_id = "sess_" + hashlib.sha256(session_seed.encode()).hexdigest()[:12]
    result["session_id"] = session_id

    # System prompt deduplication: only include if first time or changed
    if system_prompt:
        sp_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
        with _session_lock:
            prev_hash = _session_system_prompts.get(session_id)
            if prev_hash != sp_hash:
                # Evict oldest entries if cache is full
                if len(_session_system_prompts) >= _SESSION_CACHE_MAX:
                    # Remove first ~10% of entries (oldest by insertion order)
                    to_remove = list(_session_system_prompts.keys())[:_SESSION_CACHE_MAX // 10]
                    for k in to_remove:
                        del _session_system_prompts[k]
                # First time or changed — store it
                _session_system_prompts[session_id] = sp_hash
                result["system_prompt"] = system_prompt
            # else: same as before — don't store again

    return result


# ─── Heartbeat State ──────────────────────────────────────────────────────────

def _update_heartbeat_state(success: bool = True, latency_ms: int = 0):
    """Update heartbeat.json instead of writing a full ECP record.

    Heartbeats are uptime evidence, not behavior evidence.
    One summary per day is enough — no need for 48 individual records.
    """
    from datetime import datetime, timezone

    ecp_dir = Path(os.environ.get("ATLAST_ECP_DIR", os.environ.get("ECP_DIR", os.path.expanduser("~/.ecp"))))
    hb_path = ecp_dir / "heartbeat.json"

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    # Load existing state
    state = {}
    if hb_path.exists():
        try:
            state = json.loads(hb_path.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}

    # Reset counters if new day
    if state.get("date") != today:
        state = {
            "date": today,
            "total": 0,
            "success": 0,
            "failed": 0,
            "first_seen": now.isoformat(),
            "last_seen": now.isoformat(),
        }

    state["total"] = state.get("total", 0) + 1
    if success:
        state["success"] = state.get("success", 0) + 1
    else:
        state["failed"] = state.get("failed", 0) + 1
    state["last_seen"] = now.isoformat()
    state["status"] = "online"

    hb_path.write_text(json.dumps(state, indent=2))


# ─── ECP Recording ────────────────────────────────────────────────────────────

def _record_ecp(req_body: bytes, resp_content: str, path: str, provider: str,
                agent: str, model: str, latency_ms: int,
                tokens_in: Optional[int] = None, tokens_out: Optional[int] = None,
                http_status: int = 200,
                stop_reason: Optional[str] = None,
                tool_calls: Optional[list] = None,
                is_streaming: bool = False,
                is_provider_error: bool = False):
    """Fire-and-forget ECP recording in background thread."""
    # Classify infra errors (not the agent's fault) — legacy, kept for backward compat
    INFRA_STATUSES = {429: "rate_limit", 500: "server_error", 502: "bad_gateway",
                      503: "service_unavailable", 504: "gateway_timeout"}
    is_infra = http_status in INFRA_STATUSES
    error_type = INFRA_STATUSES.get(http_status)
    is_client_error = 400 <= http_status < 500 and not is_infra

    def _do_record():
        try:
            import hashlib

            meta_model = model if model != "unknown" else None

            # Extract only new content (not repeated history)
            extracted = _extract_new_content(req_body, provider)

            # Hash the full response for audit verification
            resp_bytes = resp_content.encode("utf-8") if isinstance(resp_content, str) else resp_content
            full_response_hash = "sha256:" + hashlib.sha256(resp_bytes).hexdigest()

            # Detect heartbeat: input contains HEARTBEAT (system-injected prompt)
            is_heartbeat = False
            input_text = extracted.get("input", "") or ""
            if "HEARTBEAT" in input_text:
                is_heartbeat = True

            # Heartbeat → update heartbeat.json, skip record creation
            if is_heartbeat:
                try:
                    _update_heartbeat_state(
                        success=not is_provider_error and not is_client_error and not is_infra,
                        latency_ms=latency_ms,
                    )
                except Exception:
                    pass  # Fail-Open
                return  # Skip recording

            # Detect provider error from response body (billing, quota, auth)
            detected_provider_error = is_provider_error
            if not detected_provider_error and http_status < 500:
                try:
                    resp_json = json.loads(resp_content)
                    if resp_json.get("type") == "error" or resp_json.get("error"):
                        detected_provider_error = True
                except (json.JSONDecodeError, ValueError):
                    pass

            # Has tool calls? = conversation is NOT done yet
            has_tool_calls = bool(tool_calls) or stop_reason in ("tool_use", "tool_calls")

            session_id = extracted.get("session_id") or "unknown"
            is_continuation = extracted.get("is_tool_continuation", False)

            # Extract clean text from response JSON
            clean_output = resp_content
            try:
                rj = json.loads(resp_content)
                # OpenAI format
                if "choices" in rj:
                    msg = rj["choices"][0].get("message", {})
                    clean_output = msg.get("content") or msg.get("reasoning") or resp_content
                # Anthropic format
                elif "content" in rj and isinstance(rj["content"], list):
                    texts = [b.get("text","") for b in rj["content"] if isinstance(b,dict) and b.get("type")=="text"]
                    if texts:
                        clean_output = "\n".join(texts)
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                pass
            clean_output = clean_output.strip() if isinstance(clean_output, str) else clean_output

            # Build step data for this API call
            step_data = {
                "input": extracted["input"],
                "output": clean_output,
                "model": meta_model,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tool_calls": tool_calls,
                "is_streaming": is_streaming,
                "is_infra": is_infra,
                "is_provider_error": detected_provider_error,
                "system_prompt": extracted.get("system_prompt"),
                "full_request_hash": extracted.get("full_request_hash"),
                "stop_reason": stop_reason,
                "http_status": http_status,
            }

            # ── Conversation aggregation ──
            # If this is a tool_continuation → add to existing buffer
            # If this returns tool_use → buffer it, don't write yet
            # If this is a final response (no tool_use) → flush buffer as one record

            if is_continuation:
                # This is a tool_result follow-up → add to buffer
                with _conv_lock:
                    if session_id not in _conversation_buffers:
                        # Orphaned continuation (no buffer) → create one
                        _conversation_buffers[session_id] = {
                            "agent": agent,
                            "steps": [],
                            "last_update": time.time(),
                        }
                    _conversation_buffers[session_id]["steps"].append(step_data)
                    _conversation_buffers[session_id]["last_update"] = time.time()

                if not has_tool_calls:
                    # Final response — flush the whole conversation as one record
                    _flush_conversation(session_id)
                # else: still more tool calls coming, keep buffering

            elif has_tool_calls:
                # New user message but agent returned tool_use → start buffer
                # Flush any stale buffer for this session first
                _flush_conversation(session_id)
                with _conv_lock:
                    _conversation_buffers[session_id] = {
                        "agent": agent,
                        "steps": [step_data],
                        "last_update": time.time(),
                    }
                # Don't write record yet — wait for final response

            else:
                # Simple single-turn conversation (no tool calls)
                # Write immediately as one record
                _flush_conversation(session_id)  # flush any stale buffer

                agg_flags = []
                if is_streaming:
                    agg_flags.append("streaming")
                if is_infra:
                    agg_flags.append("infra_error")
                if is_client_error:
                    agg_flags.append("client_error")
                if detected_provider_error:
                    agg_flags.append("provider_error")

                from .signals import detect_flags
                behavioral = detect_flags(
                    resp_content,
                    latency_ms=latency_ms,
                )
                for f in behavioral:
                    if f not in agg_flags:
                        agg_flags.append(f)

                vault_extra = {
                    "vault_version": 2,
                    "system_prompt": extracted["system_prompt"],
                    "full_request_hash": extracted["full_request_hash"],
                    "full_response_hash": full_response_hash,
                    "session_id": session_id,
                    "http_status": http_status,
                    "stop_reason": stop_reason,
                }

                from .core import record_minimal_v2
                record_minimal_v2(
                    input_content=extracted["input"],
                    output_content=clean_output,
                    agent=agent,
                    action=_detect_action(path),
                    model=meta_model,
                    latency_ms=latency_ms,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    session_id=session_id,
                    thread_id=session_id,  # Thread = session for proxy conversations
                    flags=list(set(agg_flags)) if agg_flags else None,
                    vault_extra=vault_extra,
                )

            # Periodic cleanup of stale buffers
            _cleanup_stale_buffers()

        except Exception:
            pass  # Fail-Open

    t = threading.Thread(target=_do_record, daemon=True)
    t.start()


# ─── Proxy Handler ────────────────────────────────────────────────────────────

class ATLASTProxy:
    """Transparent HTTP proxy that records ECP evidence from LLM API calls."""

    def __init__(self, port: int = 8340, agent: str = "proxy"):
        self.port = port
        self.agent = agent
        self.record_count = 0
        self._app = None
        self._model_agent_cache = {}  # model → agent name

    def _agent_for_request(self, model: str, req_body: bytes = b"") -> str:
        """Derive agent name from request. Priority:
        1. System prompt identity (e.g. "You are capital-manager") → capital-manager
        2. Model name (e.g. z-ai/glm-5.1 → glm-5.1)
        3. Fallback to self.agent
        """
        # Try to extract agent identity from system prompt
        if req_body:
            try:
                body = json.loads(req_body)
                messages = body.get("messages", [])
                for msg in messages:
                    if msg.get("role") == "system":
                        sys_content = msg.get("content", "")
                        if sys_content:
                            # Look for "You are {name}" or "I am {name}" patterns
                            import re
                            # Match: "You are capital-manager" or "You are Elena"
                            m = re.search(r'(?:You are|I am|name is|called)\s+([A-Za-z][A-Za-z0-9_-]{1,30})', sys_content)
                            if m:
                                agent_id = m.group(1).lower()
                                # Cache by system prompt hash + model
                                cache_key = agent_id + ":" + (model or "")
                                self._model_agent_cache[cache_key] = agent_id
                                return agent_id
                        break  # Only check first system message
            except (json.JSONDecodeError, KeyError):
                pass

        if not model:
            return self.agent

        if model in self._model_agent_cache:
            return self._model_agent_cache[model]

        # Derive from model name
        name = model.split("/")[-1] if "/" in model else model
        import re
        name = re.sub(r'-\d{8,}$', '', name)
        name = name.replace(":free", "")
        self._model_agent_cache[model] = name
        return name

    async def handle(self, request: web.Request) -> web.StreamResponse:
        """Main proxy handler — forward request, record ECP, return response."""
        t_start = time.time()

        # Read request body
        req_body = await request.read()

        # Detect provider and upstream
        provider = _detect_provider(request.path)
        upstream = _resolve_upstream(dict(request.headers), provider)
        model = _extract_model_from_request(req_body)

        # Copy headers (remove hop-by-hop)
        headers = {}
        skip_headers = {"host", "transfer-encoding", "x-real-api-url"}
        for k, v in request.headers.items():
            if k.lower() not in skip_headers:
                headers[k] = v

        target_url = upstream + request.path_qs

        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=300, connect=10, sock_read=120)
            connector = TCPConnector(ssl=True)
            async with ClientSession(connector=connector, timeout=timeout) as session:
                async with session.request(
                    request.method,
                    target_url,
                    headers=headers,
                    data=req_body,
                    allow_redirects=False,
                ) as resp:
                    content_type = resp.headers.get("content-type", "")

                    if "text/event-stream" in content_type:
                        return await self._handle_streaming(
                            request, resp, req_body, provider, model, t_start
                        )
                    else:
                        return await self._handle_sync(
                            request, resp, req_body, provider, model, t_start
                        )
        except Exception as e:
            # Fail-Open: record the proxy-level error, then return error
            latency_ms = int((time.time() - t_start) * 1000)
            error_msg = json.dumps({"error": f"ATLAST Proxy error: {str(e)}"})
            _record_ecp(req_body, error_msg, request.path, provider,
                         self._agent_for_request(model, req_body), model, latency_ms, http_status=502)
            self.record_count += 1
            return web.Response(
                text=error_msg,
                status=502,
                content_type="application/json",
            )

    async def _handle_sync(self, request, resp, req_body, provider, model, t_start):
        """Handle synchronous (non-streaming) response."""
        resp_body = await resp.read()
        latency_ms = int((time.time() - t_start) * 1000)

        # Build response headers (filter hop-by-hop)
        resp_headers = {}
        skip = {"transfer-encoding", "connection", "content-encoding", "content-length"}
        for k, v in resp.headers.items():
            if k.lower() not in skip:
                resp_headers[k] = v

        # Record ECP (including infra errors like 429/500/503)
        tokens_in, tokens_out = _extract_tokens_from_response(resp_body, provider)
        resp_text = resp_body.decode("utf-8", errors="replace")

        # Extract stop_reason and tool_calls from sync response
        sync_stop_reason = None
        sync_tool_calls = []
        sync_is_error = False
        try:
            resp_json = json.loads(resp_body)
            if provider == "ollama":
                # Ollama native /api/chat format
                msg = resp_json.get("message", {})
                sync_stop_reason = "stop" if resp_json.get("done") else None
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {})
                        sync_tool_calls.append({"name": fn.get("name", ""), "input": fn.get("arguments", {})})
            elif provider in ("openai", "minimax"):
                for choice in resp_json.get("choices", []):
                    sync_stop_reason = choice.get("finish_reason")
                    msg = choice.get("message", {})
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            fn = tc.get("function", {})
                            try:
                                inp = json.loads(fn.get("arguments", "{}"))
                            except (json.JSONDecodeError, ValueError):
                                inp = fn.get("arguments", "")
                            sync_tool_calls.append({"name": fn.get("name", ""), "input": inp})
            elif provider == "anthropic":
                sync_stop_reason = resp_json.get("stop_reason")
                for block in resp_json.get("content", []):
                    if block.get("type") == "tool_use":
                        sync_tool_calls.append({"name": block.get("name", ""), "input": block.get("input", {})})
            if resp_json.get("type") == "error" or resp_json.get("error"):
                sync_is_error = True
        except (json.JSONDecodeError, ValueError):
            pass

        _record_ecp(req_body, resp_text, request.path, provider,
                     self._agent_for_request(model, req_body), model, latency_ms, tokens_in, tokens_out,
                     http_status=resp.status,
                     stop_reason=sync_stop_reason,
                     tool_calls=sync_tool_calls if sync_tool_calls else None,
                     is_streaming=False,
                     is_provider_error=sync_is_error)
        self.record_count += 1

        return web.Response(
            body=resp_body,
            status=resp.status,
            headers=resp_headers,
        )

    async def _handle_streaming(self, request, resp, req_body, provider, model, t_start):
        """Handle SSE streaming response."""
        # Build response headers
        resp_headers = {}
        skip = {"transfer-encoding", "connection", "content-encoding", "content-length"}
        for k, v in resp.headers.items():
            if k.lower() not in skip:
                resp_headers[k] = v

        response = web.StreamResponse(
            status=resp.status,
            headers=resp_headers,
        )
        await response.prepare(request)

        chunks = []
        try:
            async for chunk in resp.content.iter_any():
                chunks.append(chunk)
                await response.write(chunk)
        except Exception:
            pass  # Client disconnect is OK

        # Record ECP from buffered chunks
        latency_ms = int((time.time() - t_start) * 1000)
        full_response = b"".join(chunks)
        sse_result = _reconstruct_sse_content(full_response, provider)
        # Extract tokens from SSE (OpenAI final chunk, Anthropic message_start/delta)
        sse_tokens_in = sse_result.get("tokens_in")
        sse_tokens_out = sse_result.get("tokens_out")
        _record_ecp(req_body, sse_result["content"], request.path, provider,
                     self._agent_for_request(model, req_body), model, latency_ms,
                     tokens_in=sse_tokens_in, tokens_out=sse_tokens_out,
                     stop_reason=sse_result.get("stop_reason"),
                     tool_calls=sse_result.get("tool_calls"),
                     is_streaming=True,
                     is_provider_error=sse_result.get("is_error", False),
                     http_status=resp.status)
        self.record_count += 1

        try:
            await response.write_eof()
        except Exception:
            pass

        return response

    def create_app(self) -> web.Application:
        """Create aiohttp application."""
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self.handle)
        self._app = app
        return app


# ─── Entry Points ─────────────────────────────────────────────────────────────

def run_proxy(port: int = 8340, agent: str = "proxy"):
    """Start the ATLAST Proxy (blocking). Called by 'atlast proxy'."""
    if not HAS_AIOHTTP:
        print("Error: aiohttp required. Install with: pip install atlast-ecp[proxy]")
        sys.exit(1)

    proxy = ATLASTProxy(port=port, agent=agent)
    app = proxy.create_app()

    print("\n🔗 ATLAST Proxy — Evidence Chain Protocol")
    print(f"   Listening: http://localhost:{port}")
    print(f"   Agent: {agent}")
    print("   Records: ~/.ecp/records/")
    print("\n   Set your LLM client to use this proxy:")
    print(f"     OPENAI_BASE_URL=http://localhost:{port}")
    print(f"     ANTHROPIC_BASE_URL=http://localhost:{port}")
    print("\n   Or use: atlast run python my_agent.py")
    print("\n   Press Ctrl+C to stop.\n")

    # Start batch scheduler (auto-upload Merkle root every hour)
    try:
        from .batch import start_scheduler
        start_scheduler(interval_seconds=3600)
        print("   📦 Batch scheduler: every 60 min → chain anchor\n")
    except Exception:
        pass  # Fail-Open

    web.run_app(app, host="127.0.0.1", port=port, print=None)


def _find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_with_proxy(command_args: list[str]):
    """Run a command with ATLAST Proxy auto-injected. Called by 'atlast run'."""
    if not HAS_AIOHTTP:
        print("Error: aiohttp required. Install with: pip install atlast-ecp[proxy]")
        sys.exit(1)

    port = _find_free_port()
    proxy = ATLASTProxy(port=port, agent="proxy")

    # Start proxy in background thread
    loop = asyncio.new_event_loop()
    app = proxy.create_app()
    runner = web.AppRunner(app)

    async def _start():
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()

    loop.run_until_complete(_start())
    proxy_thread = threading.Thread(target=loop.run_forever, daemon=True)
    proxy_thread.start()

    # Wait for proxy to be ready
    time.sleep(0.3)

    print(f"🔗 ATLAST Proxy started on port {port}")
    print(f"   Recording ECP evidence for: {' '.join(command_args)}\n")

    # Build modified environment
    env = os.environ.copy()

    # Save originals so proxy can forward to real APIs
    if "OPENAI_BASE_URL" in env:
        env["OPENAI_BASE_URL_ORIGINAL"] = env["OPENAI_BASE_URL"]
    if "OPENAI_API_BASE" in env:
        env["OPENAI_API_BASE_ORIGINAL"] = env["OPENAI_API_BASE"]
    if "ANTHROPIC_BASE_URL" in env:
        env["ANTHROPIC_BASE_URL_ORIGINAL"] = env["ANTHROPIC_BASE_URL"]

    # Point all SDKs to our proxy
    proxy_url = f"http://127.0.0.1:{port}"
    env["OPENAI_BASE_URL"] = proxy_url
    env["OPENAI_API_BASE"] = proxy_url       # Legacy
    env["ANTHROPIC_BASE_URL"] = proxy_url

    # Run the user's command
    t_start = time.time()
    try:
        result = subprocess.run(command_args, env=env)
        exit_code = result.returncode
    except KeyboardInterrupt:
        exit_code = 130
    except FileNotFoundError:
        print(f"Error: command not found: {command_args[0]}")
        exit_code = 127

    # Cleanup
    duration = time.time() - t_start
    loop.call_soon_threadsafe(loop.stop)

    print(f"\n{'─' * 50}")
    print("🔗 ATLAST ECP Summary")
    print(f"   Records created: {proxy.record_count}")
    print(f"   Duration: {duration:.1f}s")
    print("   Storage: ~/.ecp/records/")
    print("   View: atlast log")

    sys.exit(exit_code)
