"""Integration tests for ATLAST Proxy — real HTTP round-trip tests.

Spins up mock upstream + ATLAST Proxy, sends real HTTP requests through.
Uses threading + aiohttp directly (no pytest-asyncio dependency).
"""

import asyncio
import json
import os
import shutil
import tempfile
import threading
import time

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web, ClientSession
from aiohttp.test_utils import unused_port


# ─── Mock Upstream Handlers ───────────────────────────────────────────────────

async def _mock_chat_completions(request):
    body = await request.json()
    model = body.get("model", "gpt-4")
    stream = body.get("stream", False)

    if stream:
        resp = web.StreamResponse(status=200, headers={
            "Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(request)
        for chunk_text in ["Hello", " from", " streaming", " mock!"]:
            data = {"id": "chatcmpl-s", "object": "chat.completion.chunk", "model": model,
                    "choices": [{"index": 0, "delta": {"content": chunk_text}, "finish_reason": None}]}
            await resp.write(f"data: {json.dumps(data)}\n\n".encode())
            await asyncio.sleep(0.01)
        final = {"id": "chatcmpl-s", "object": "chat.completion.chunk", "model": model,
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        await resp.write(f"data: {json.dumps(final)}\n\n".encode())
        await resp.write(b"data: [DONE]\n\n")
        await resp.write_eof()
        return resp
    else:
        return web.json_response({
            "id": "chatcmpl-test123", "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello from mock!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })


async def _mock_anthropic_messages(request):
    body = await request.json()
    stream = body.get("stream", False)

    if stream:
        resp = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        for text in ["Hello", " Anthropic", " stream!"]:
            d = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}
            await resp.write(f"data: {json.dumps(d)}\n\n".encode())
            await asyncio.sleep(0.01)
        await resp.write(b'data: {"type":"message_stop"}\n\n')
        await resp.write_eof()
        return resp
    else:
        return web.json_response({
            "id": "msg_test", "type": "message", "role": "assistant",
            "content": [{"type": "text", "text": "Hello from Anthropic mock!"}],
            "model": "claude-sonnet-4-20250514", "usage": {"input_tokens": 12, "output_tokens": 8},
        })


async def _mock_500(request):
    return web.Response(status=500, text='{"error":"fail"}', content_type="application/json")


# ─── Server Helpers ───────────────────────────────────────────────────────────

def _start_server_in_thread(app, port):
    """Start an aiohttp app in a background thread, return (loop, runner, thread)."""
    loop = asyncio.new_event_loop()
    runner = web.AppRunner(app)

    async def _start():
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()

    loop.run_until_complete(_start())
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    time.sleep(0.2)
    return loop, runner, t


def _stop_server(loop, runner):
    async def _cleanup():
        await runner.cleanup()
    loop.call_soon_threadsafe(loop.stop)
    time.sleep(0.1)


def _run_async(coro):
    """Run an async function synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ecp_dir(tmp_path):
    d = tmp_path / "ecp"
    d.mkdir()
    old = os.environ.get("ATLAST_ECP_DIR")
    os.environ["ATLAST_ECP_DIR"] = str(d)
    yield d
    if old:
        os.environ["ATLAST_ECP_DIR"] = old
    else:
        os.environ.pop("ATLAST_ECP_DIR", None)


@pytest.fixture
def servers(ecp_dir):
    """Start mock upstream + ATLAST proxy. Yields dict with ports and proxy instance."""
    from atlast_ecp.proxy import ATLASTProxy

    # Mock upstream
    upstream_port = unused_port()
    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/chat/completions", _mock_chat_completions)
    upstream_app.router.add_post("/v1/messages", _mock_anthropic_messages)
    u_loop, u_runner, u_thread = _start_server_in_thread(upstream_app, upstream_port)

    # ATLAST Proxy
    proxy_port = unused_port()
    proxy = ATLASTProxy(port=proxy_port, agent="test-agent")
    proxy_app = proxy.create_app()
    p_loop, p_runner, p_thread = _start_server_in_thread(proxy_app, proxy_port)

    # Point proxy at mock upstream
    old_env = os.environ.get("ATLAST_UPSTREAM_URL")
    os.environ["ATLAST_UPSTREAM_URL"] = f"http://127.0.0.1:{upstream_port}"

    yield {
        "proxy_port": proxy_port,
        "upstream_port": upstream_port,
        "proxy": proxy,
        "ecp_dir": ecp_dir,
    }

    # Cleanup
    os.environ.pop("ATLAST_UPSTREAM_URL", None)
    if old_env:
        os.environ["ATLAST_UPSTREAM_URL"] = old_env
    _stop_server(p_loop, p_runner)
    _stop_server(u_loop, u_runner)


@pytest.fixture
def error_servers(ecp_dir):
    """Mock upstream that always 500 + proxy."""
    from atlast_ecp.proxy import ATLASTProxy

    upstream_port = unused_port()
    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/chat/completions", _mock_500)
    u_loop, u_runner, _ = _start_server_in_thread(upstream_app, upstream_port)

    proxy_port = unused_port()
    proxy = ATLASTProxy(port=proxy_port, agent="test-agent")
    p_loop, p_runner, _ = _start_server_in_thread(proxy.create_app(), proxy_port)

    os.environ["ATLAST_UPSTREAM_URL"] = f"http://127.0.0.1:{upstream_port}"
    yield {"proxy_port": proxy_port, "proxy": proxy, "ecp_dir": ecp_dir}
    os.environ.pop("ATLAST_UPSTREAM_URL", None)
    _stop_server(p_loop, p_runner)
    _stop_server(u_loop, u_runner)


# ─── Sync Forwarding Tests ───────────────────────────────────────────────────

class TestSyncForwarding:

    def test_openai_round_trip(self, servers):
        async def _test():
            url = f"http://127.0.0.1:{servers['proxy_port']}/v1/chat/completions"
            async with ClientSession() as s:
                async with s.post(url, json={"model": "gpt-4", "messages": [{"role": "user", "content": "Hi"}]},
                                  headers={"Authorization": "Bearer sk-test"}) as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["choices"][0]["message"]["content"] == "Hello from mock!"
                    assert data["usage"]["prompt_tokens"] == 10
        _run_async(_test())

    def test_anthropic_round_trip(self, servers):
        async def _test():
            url = f"http://127.0.0.1:{servers['proxy_port']}/v1/messages"
            async with ClientSession() as s:
                async with s.post(url, json={"model": "claude-sonnet-4-20250514", "max_tokens": 100,
                                             "messages": [{"role": "user", "content": "Hi"}]},
                                  headers={"x-api-key": "sk-ant-test", "anthropic-version": "2023-06-01"}) as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["content"][0]["text"] == "Hello from Anthropic mock!"
        _run_async(_test())

    def test_ecp_record_created(self, servers):
        async def _test():
            url = f"http://127.0.0.1:{servers['proxy_port']}/v1/chat/completions"
            async with ClientSession() as s:
                async with s.post(url, json={"model": "gpt-4", "messages": [{"role": "user", "content": "Record me"}]}) as resp:
                    assert resp.status == 200
        _run_async(_test())
        time.sleep(0.5)  # background thread writes
        assert servers["proxy"].record_count >= 1
        # Check files
        records_dir = servers["ecp_dir"] / "records"
        if records_dir.exists():
            files = list(records_dir.glob("*.jsonl"))
            assert len(files) >= 1
            content = files[0].read_text().strip()
            rec = json.loads(content.split("\n")[0])
            assert rec.get("ecp") in ("0.1", "1.0")
            assert "in_hash" in rec
            assert "out_hash" in rec

    def test_multiple_requests(self, servers):
        async def _test():
            url = f"http://127.0.0.1:{servers['proxy_port']}/v1/chat/completions"
            async with ClientSession() as s:
                for i in range(3):
                    async with s.post(url, json={"model": "gpt-4", "messages": [{"role": "user", "content": f"msg {i}"}]}) as resp:
                        assert resp.status == 200
        _run_async(_test())
        time.sleep(0.5)
        assert servers["proxy"].record_count == 3


# ─── Streaming Tests ──────────────────────────────────────────────────────────

class TestStreamingForwarding:

    def test_openai_sse_streaming(self, servers):
        async def _test():
            url = f"http://127.0.0.1:{servers['proxy_port']}/v1/chat/completions"
            payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "Stream"}], "stream": True}
            chunks = []
            async with ClientSession() as s:
                async with s.post(url, json=payload) as resp:
                    assert resp.status == 200
                    assert "text/event-stream" in resp.headers.get("Content-Type", "")
                    async for line in resp.content:
                        decoded = line.decode("utf-8").strip()
                        if decoded.startswith("data: ") and decoded != "data: [DONE]":
                            try:
                                data = json.loads(decoded[6:])
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                if "content" in delta:
                                    chunks.append(delta["content"])
                            except json.JSONDecodeError:
                                pass
            return "".join(chunks)
        result = _run_async(_test())
        assert result == "Hello from streaming mock!"

    def test_anthropic_sse_streaming(self, servers):
        async def _test():
            url = f"http://127.0.0.1:{servers['proxy_port']}/v1/messages"
            payload = {"model": "claude-sonnet-4-20250514", "max_tokens": 100,
                       "messages": [{"role": "user", "content": "Stream"}], "stream": True}
            deltas = []
            async with ClientSession() as s:
                async with s.post(url, json=payload, headers={"x-api-key": "test", "anthropic-version": "2023-06-01"}) as resp:
                    assert resp.status == 200
                    async for line in resp.content:
                        decoded = line.decode("utf-8").strip()
                        if decoded.startswith("data: "):
                            try:
                                data = json.loads(decoded[6:])
                                if data.get("type") == "content_block_delta":
                                    deltas.append(data["delta"]["text"])
                            except json.JSONDecodeError:
                                pass
            return "".join(deltas)
        result = _run_async(_test())
        assert result == "Hello Anthropic stream!"

    def test_streaming_creates_ecp_record(self, servers):
        async def _test():
            url = f"http://127.0.0.1:{servers['proxy_port']}/v1/chat/completions"
            payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "test"}], "stream": True}
            async with ClientSession() as s:
                async with s.post(url, json=payload) as resp:
                    async for _ in resp.content:
                        pass
        _run_async(_test())
        time.sleep(0.5)
        assert servers["proxy"].record_count >= 1


# ─── Fail-Open Tests ──────────────────────────────────────────────────────────

class TestFailOpen:

    def test_upstream_500_forwarded(self, error_servers):
        async def _test():
            url = f"http://127.0.0.1:{error_servers['proxy_port']}/v1/chat/completions"
            async with ClientSession() as s:
                async with s.post(url, json={"model": "gpt-4", "messages": [{"role": "user", "content": "fail"}]}) as resp:
                    return resp.status
        status = _run_async(_test())
        assert status == 500

    def test_unreachable_upstream_returns_502(self, ecp_dir):
        from atlast_ecp.proxy import ATLASTProxy
        os.environ["ATLAST_UPSTREAM_URL"] = "http://127.0.0.1:1"  # unreachable
        proxy_port = unused_port()
        proxy = ATLASTProxy(port=proxy_port, agent="test")
        p_loop, p_runner, _ = _start_server_in_thread(proxy.create_app(), proxy_port)

        try:
            async def _test():
                url = f"http://127.0.0.1:{proxy_port}/v1/chat/completions"
                async with ClientSession() as s:
                    async with s.post(url, json={"model": "gpt-4", "messages": [{"role": "user", "content": "x"}]}) as resp:
                        data = await resp.json()
                        return resp.status, data
            status, data = _run_async(_test())
            assert status == 502
            assert "error" in data
        finally:
            os.environ.pop("ATLAST_UPSTREAM_URL", None)
            _stop_server(p_loop, p_runner)


# ─── Utility Tests ────────────────────────────────────────────────────────────

class TestFindFreePort:
    def test_returns_valid_port(self):
        from atlast_ecp.proxy import _find_free_port
        port = _find_free_port()
        assert 1024 <= port <= 65535

    def test_different_ports(self):
        from atlast_ecp.proxy import _find_free_port
        ports = {_find_free_port() for _ in range(5)}
        assert len(ports) >= 2
