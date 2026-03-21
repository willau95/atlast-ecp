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
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Optional

# aiohttp is optional dependency
try:
    from aiohttp import web, ClientSession, TCPConnector
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ─── Provider Detection ───────────────────────────────────────────────────────

# Map of path patterns → provider name
PROVIDER_ROUTES = {
    "/v1/chat/completions": "openai",      # OpenAI + all compatible (Qwen, Kimi, DeepSeek, Yi, Groq, Together)
    "/v1/completions": "openai",            # Legacy completions
    "/v1/embeddings": "openai",             # Embeddings
    "/v1/messages": "anthropic",            # Anthropic
    "/v1/text/chatcompletion": "minimax",   # MiniMax
}


def _detect_provider(path: str) -> str:
    """Detect API provider from request path."""
    for pattern, provider in PROVIDER_ROUTES.items():
        if path.startswith(pattern):
            return provider
    if "/v1beta/models/" in path and "generateContent" in path:
        return "gemini"
    return "unknown"


def _detect_action(path: str) -> str:
    """Map request path to ECP action type."""
    if "chat/completions" in path or "messages" in path or "chatcompletion" in path or "generateContent" in path:
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
}

# Env vars that might contain the original upstream URL
UPSTREAM_ENV_VARS = [
    "ATLAST_UPSTREAM_URL",       # Explicit override
    "ATLAST_OPENAI_UPSTREAM",    # Per-provider
    "ATLAST_ANTHROPIC_UPSTREAM",
    "OPENAI_API_BASE",           # Legacy OpenAI
    "OPENAI_BASE_URL_ORIGINAL",  # Saved by atlast run
    "ANTHROPIC_BASE_URL_ORIGINAL",
]


def _resolve_upstream(request_headers: dict, provider: str) -> str:
    """Determine the real upstream API URL."""
    # 1. Explicit header override
    explicit = request_headers.get("X-Real-API-URL") or request_headers.get("x-real-api-url")
    if explicit:
        return explicit.rstrip("/")

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
    """Extract token counts from response body. Returns (tokens_in, tokens_out)."""
    try:
        data = json.loads(body)
        usage = data.get("usage", {})
        if provider == "openai":
            return usage.get("prompt_tokens"), usage.get("completion_tokens")
        elif provider == "anthropic":
            return usage.get("input_tokens"), usage.get("output_tokens")
        return None, None
    except Exception:
        return None, None


def _reconstruct_sse_content(chunks: bytes, provider: str) -> str:
    """Reconstruct full response content from SSE stream chunks."""
    try:
        text = chunks.decode("utf-8", errors="replace")
        content_parts = []
        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                continue
            try:
                data = json.loads(data_str)
                if provider in ("openai", "minimax"):
                    # OpenAI streaming format
                    for choice in data.get("choices", []):
                        delta = choice.get("delta", {})
                        if "content" in delta and delta["content"]:
                            content_parts.append(delta["content"])
                elif provider == "anthropic":
                    # Anthropic streaming format
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("text"):
                            content_parts.append(delta["text"])
            except json.JSONDecodeError:
                continue
        return "".join(content_parts)
    except Exception:
        return chunks.decode("utf-8", errors="replace")


# ─── ECP Recording ────────────────────────────────────────────────────────────

def _record_ecp(req_body: bytes, resp_content: str, path: str, provider: str,
                agent: str, model: str, latency_ms: int,
                tokens_in: Optional[int] = None, tokens_out: Optional[int] = None):
    """Fire-and-forget ECP recording in background thread."""
    def _do_record():
        try:
            from .core import record_minimal
            meta_model = model if model != "unknown" else None
            record_minimal(
                input_content=req_body.decode("utf-8", errors="replace"),
                output_content=resp_content,
                agent=agent,
                action=_detect_action(path),
                model=meta_model,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
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
        self._runner = None

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
            connector = TCPConnector(ssl=True)
            async with ClientSession(connector=connector) as session:
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
            # Fail-Open: if proxy fails, return error but don't crash
            return web.Response(
                text=json.dumps({"error": f"ATLAST Proxy error: {str(e)}"}),
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

        # Record ECP
        tokens_in, tokens_out = _extract_tokens_from_response(resp_body, provider)
        resp_text = resp_body.decode("utf-8", errors="replace")
        _record_ecp(req_body, resp_text, request.path, provider,
                     self.agent, model, latency_ms, tokens_in, tokens_out)
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
        resp_content = _reconstruct_sse_content(full_response, provider)
        _record_ecp(req_body, resp_content, request.path, provider,
                     self.agent, model, latency_ms)
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

    print(f"\n🔗 ATLAST Proxy — Evidence Chain Protocol")
    print(f"   Listening: http://localhost:{port}")
    print(f"   Agent: {agent}")
    print(f"   Records: ~/.ecp/records/")
    print(f"\n   Set your LLM client to use this proxy:")
    print(f"     OPENAI_BASE_URL=http://localhost:{port}")
    print(f"     ANTHROPIC_BASE_URL=http://localhost:{port}")
    print(f"\n   Or use: atlast run python my_agent.py")
    print(f"\n   Press Ctrl+C to stop.\n")

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
    print(f"🔗 ATLAST ECP Summary")
    print(f"   Records created: {proxy.record_count}")
    print(f"   Duration: {duration:.1f}s")
    print(f"   Storage: ~/.ecp/records/")
    print(f"   View: atlast log")

    sys.exit(exit_code)
