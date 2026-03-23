"""
Tests for P5: SDK Retry + Exponential Backoff.
Verifies that upload_merkle_root retries on transient errors
and fails fast on permanent errors.
"""

import json
import time
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from atlast_ecp.batch import upload_merkle_root


class TestUploadRetry(unittest.TestCase):
    """Test exponential backoff retry logic in upload_merkle_root."""

    @patch("atlast_ecp.batch._get_api_url", return_value="http://localhost:9999")
    @patch("atlast_ecp.batch.urllib.request.urlopen")
    def test_success_first_try(self, mock_urlopen, _):
        """Upload succeeds on first attempt — no retries."""
        resp = MagicMock()
        resp.read.return_value = json.dumps({"batch_id": "b_123"}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = upload_merkle_root(
            merkle_root="sha256:abc",
            agent_did="did:ecp:test",
            record_count=5,
            avg_latency_ms=100,
            batch_ts=1234567890,
            sig="ed25519:test",
        )
        self.assertEqual(result, "b_123")
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("atlast_ecp.batch._get_api_url", return_value="http://localhost:9999")
    @patch("atlast_ecp.batch.time.sleep")
    @patch("atlast_ecp.batch.urllib.request.urlopen")
    def test_retry_on_503_then_success(self, mock_urlopen, mock_sleep, _):
        """503 triggers retry; succeeds on 2nd attempt."""
        # First call: 503
        err_503 = urllib.error.HTTPError(
            "http://localhost", 503, "Service Unavailable", {}, None
        )
        # Second call: success
        resp = MagicMock()
        resp.read.return_value = json.dumps({"batch_id": "b_ok"}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [err_503, resp]

        result = upload_merkle_root(
            merkle_root="sha256:abc",
            agent_did="did:ecp:test",
            record_count=5,
            avg_latency_ms=100,
            batch_ts=1234567890,
            sig="ed25519:test",
            max_retries=3,
        )
        self.assertEqual(result, "b_ok")
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(1)  # 2^0 = 1s backoff

    @patch("atlast_ecp.batch._get_api_url", return_value="http://localhost:9999")
    @patch("atlast_ecp.batch.time.sleep")
    @patch("atlast_ecp.batch.urllib.request.urlopen")
    def test_no_retry_on_400(self, mock_urlopen, mock_sleep, _):
        """400 Bad Request = permanent error, no retry."""
        err_400 = urllib.error.HTTPError(
            "http://localhost", 400, "Bad Request", {}, None
        )
        mock_urlopen.side_effect = err_400

        result = upload_merkle_root(
            merkle_root="sha256:abc",
            agent_did="did:ecp:test",
            record_count=5,
            avg_latency_ms=100,
            batch_ts=1234567890,
            sig="ed25519:test",
            max_retries=3,
        )
        self.assertIsNone(result)
        self.assertEqual(mock_urlopen.call_count, 1)  # No retry
        mock_sleep.assert_not_called()

    @patch("atlast_ecp.batch._get_api_url", return_value="http://localhost:9999")
    @patch("atlast_ecp.batch.time.sleep")
    @patch("atlast_ecp.batch.urllib.request.urlopen")
    def test_no_retry_on_401(self, mock_urlopen, mock_sleep, _):
        """401 Unauthorized = permanent, no retry."""
        err_401 = urllib.error.HTTPError(
            "http://localhost", 401, "Unauthorized", {}, None
        )
        mock_urlopen.side_effect = err_401

        result = upload_merkle_root(
            merkle_root="sha256:abc",
            agent_did="did:ecp:test",
            record_count=5,
            avg_latency_ms=100,
            batch_ts=1234567890,
            sig="ed25519:test",
        )
        self.assertIsNone(result)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("atlast_ecp.batch._get_api_url", return_value="http://localhost:9999")
    @patch("atlast_ecp.batch.time.sleep")
    @patch("atlast_ecp.batch.urllib.request.urlopen")
    def test_retry_on_connection_error(self, mock_urlopen, mock_sleep, _):
        """Connection refused triggers retry."""
        conn_err = urllib.error.URLError("Connection refused")
        resp = MagicMock()
        resp.read.return_value = json.dumps({"batch_id": "b_retry"}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [conn_err, conn_err, resp]

        result = upload_merkle_root(
            merkle_root="sha256:abc",
            agent_did="did:ecp:test",
            record_count=5,
            avg_latency_ms=100,
            batch_ts=1234567890,
            sig="ed25519:test",
            max_retries=3,
        )
        self.assertEqual(result, "b_retry")
        self.assertEqual(mock_urlopen.call_count, 3)
        # Backoff: 1s, 2s
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch("atlast_ecp.batch._get_api_url", return_value="http://localhost:9999")
    @patch("atlast_ecp.batch.time.sleep")
    @patch("atlast_ecp.batch.urllib.request.urlopen")
    def test_all_retries_exhausted(self, mock_urlopen, mock_sleep, _):
        """All 3 retries fail → returns None (Fail-Open)."""
        err_500 = urllib.error.HTTPError(
            "http://localhost", 500, "Internal Server Error", {}, None
        )
        mock_urlopen.side_effect = [err_500, err_500, err_500]

        result = upload_merkle_root(
            merkle_root="sha256:abc",
            agent_did="did:ecp:test",
            record_count=5,
            avg_latency_ms=100,
            batch_ts=1234567890,
            sig="ed25519:test",
            max_retries=3,
        )
        self.assertIsNone(result)
        self.assertEqual(mock_urlopen.call_count, 3)
        # Backoff: 1s, 2s (not after last attempt)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("atlast_ecp.batch._get_api_url", return_value="http://localhost:9999")
    @patch("atlast_ecp.batch.time.sleep")
    @patch("atlast_ecp.batch.urllib.request.urlopen")
    def test_timeout_retries(self, mock_urlopen, mock_sleep, _):
        """Timeout errors are retried."""
        mock_urlopen.side_effect = [TimeoutError(), TimeoutError(), TimeoutError()]

        result = upload_merkle_root(
            merkle_root="sha256:abc",
            agent_did="did:ecp:test",
            record_count=5,
            avg_latency_ms=100,
            batch_ts=1234567890,
            sig="ed25519:test",
            max_retries=3,
        )
        self.assertIsNone(result)
        self.assertEqual(mock_urlopen.call_count, 3)


class TestPushRetryCommand(unittest.TestCase):
    """Test atlast push --retry CLI command."""

    @patch("atlast_ecp.batch.get_upload_queue", return_value=[])
    def test_push_retry_empty_queue(self, _):
        from atlast_ecp.cli import cmd_push
        # Should not raise
        cmd_push(["--retry"])

    @patch("atlast_ecp.batch.clear_upload_queue")
    @patch("atlast_ecp.batch.upload_merkle_root", return_value="b_123")
    @patch("atlast_ecp.batch.get_upload_queue", return_value=[{
        "merkle_root": "sha256:abc",
        "agent_did": "did:ecp:test",
        "record_count": 5,
        "avg_latency_ms": 100,
        "batch_ts": 1234567890,
        "sig": "ed25519:test",
    }])
    def test_push_retry_succeeds(self, mock_queue, mock_upload, mock_clear):
        from atlast_ecp.cli import cmd_push
        cmd_push(["--retry"])
        mock_upload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
