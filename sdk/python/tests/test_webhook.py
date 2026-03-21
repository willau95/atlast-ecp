"""Tests for ATLAST ECP Webhook — fire_webhook + build_webhook_payload."""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

from atlast_ecp.webhook import fire_webhook, build_webhook_payload


class _MockHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler for webhook testing."""
    received = []
    response_code = 200

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _MockHandler.received.append({
            "body": json.loads(body),
            "headers": dict(self.headers),
        })
        self.send_response(_MockHandler.response_code)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress output


@pytest.fixture
def mock_server():
    """Start a mock HTTP server on a random port."""
    _MockHandler.received = []
    _MockHandler.response_code = 200
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", server
    server.shutdown()


class TestBuildWebhookPayload:
    def test_basic(self):
        data = {
            "batch_id": "batch_abc",
            "agent_did": "did:ecp:xyz",
            "merkle_root": "sha256:deadbeef",
            "record_count": 5,
        }
        payload = build_webhook_payload(data)
        assert payload["event"] == "attestation.anchored"
        assert payload["cert_id"] == "batch_abc"
        assert payload["agent_did"] == "did:ecp:xyz"
        assert payload["batch_merkle_root"] == "sha256:deadbeef"
        assert payload["record_count"] == 5

    def test_all_fields(self):
        """Verify all 11 fields from CERTIFICATE-SCHEMA.md Section 3."""
        data = {
            "cert_id": "cert_abc",
            "agent_did": "did:ecp:xyz",
            "batch_merkle_root": "sha256:aaa",
            "record_count": 10,
            "attestation_uid": "0xabc",
            "eas_tx_hash": "0xdef",
            "schema_uid": "0x123",
            "chain_id": 84532,
            "on_chain": True,
            "created_at": "2026-03-20T00:00:00Z",
        }
        payload = build_webhook_payload(data)
        expected_keys = {
            "event", "cert_id", "agent_did", "batch_merkle_root", "record_count",
            "attestation_uid", "eas_tx_hash", "schema_uid", "chain_id",
            "on_chain", "created_at",
        }
        assert set(payload.keys()) == expected_keys

    def test_missing_fields_default_none(self):
        payload = build_webhook_payload({})
        assert payload["event"] == "attestation.anchored"
        assert payload["cert_id"] is None
        assert payload["on_chain"] is False


class TestFireWebhook:
    def test_success(self, mock_server):
        url, _ = mock_server
        result = fire_webhook({"test": True}, url)
        assert result is True
        assert len(_MockHandler.received) == 1
        assert _MockHandler.received[0]["body"] == {"test": True}

    def test_with_token(self, mock_server):
        url, _ = mock_server
        fire_webhook({"x": 1}, url, token="secret-token")
        hdrs = _MockHandler.received[0]["headers"]
        # Headers may be case-insensitive; check both forms
        token = hdrs.get("X-ECP-Webhook-Token") or hdrs.get("X-Ecp-Webhook-Token") or hdrs.get("x-ecp-webhook-token")
        assert token == "secret-token"

    def test_fail_open_unreachable(self):
        result = fire_webhook({"test": True}, "http://127.0.0.1:1", timeout=1)
        assert result is False  # Should not raise

    def test_retry_on_5xx(self, mock_server):
        url, _ = mock_server
        call_count = [0]
        original_response = _MockHandler.response_code

        class RetryHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                call_count[0] += 1
                if call_count[0] == 1:
                    self.send_response(500)
                else:
                    self.send_response(200)
                self.end_headers()
            def log_message(self, *a):
                pass

        retry_server = HTTPServer(("127.0.0.1", 0), RetryHandler)
        port = retry_server.server_address[1]
        t = threading.Thread(target=retry_server.serve_forever, daemon=True)
        t.start()

        result = fire_webhook({"test": True}, f"http://127.0.0.1:{port}")
        assert result is True
        assert call_count[0] == 2
        retry_server.shutdown()

    def test_no_retry_on_4xx(self, mock_server):
        url, _ = mock_server
        _MockHandler.response_code = 400
        result = fire_webhook({"test": True}, url)
        assert result is False
        assert len(_MockHandler.received) == 1  # No retry
