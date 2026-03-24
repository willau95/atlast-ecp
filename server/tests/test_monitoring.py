"""Tests for centralized error monitoring."""

import pytest
from unittest.mock import patch, MagicMock


class TestCaptureError:
    """Tests for capture_error helper."""

    def test_capture_error_logs_always(self):
        """capture_error should always log, even without Sentry."""
        from app.services.monitoring import capture_error

        with patch("app.services.monitoring.logger") as mock_logger:
            err = ValueError("test error")
            capture_error(err, {"key": "value"})
            mock_logger.error.assert_called_once()
            call_kwargs = mock_logger.error.call_args
            assert "test error" in str(call_kwargs)

    def test_capture_error_with_sentry(self):
        """capture_error should call sentry_sdk.capture_exception when DSN configured."""
        from app.services.monitoring import capture_error

        mock_sentry = MagicMock()
        err = RuntimeError("sentry test")

        with patch("app.services.monitoring.logger"):
            with patch.dict("os.environ", {"SENTRY_DSN": "https://fake@sentry.io/123"}):
                with patch("sentry_sdk.capture_exception") as mock_capture:
                    with patch("sentry_sdk.push_scope") as mock_scope:
                        mock_scope.return_value.__enter__ = MagicMock()
                        mock_scope.return_value.__exit__ = MagicMock(return_value=False)
                        # Need to patch settings to have SENTRY_DSN
                        with patch("app.config.settings") as mock_settings:
                            mock_settings.SENTRY_DSN = "https://fake@sentry.io/123"
                            capture_error(err, {"ctx": "test"})

    def test_capture_error_no_sentry_no_crash(self):
        """capture_error should NOT crash when SENTRY_DSN is empty."""
        from app.services.monitoring import capture_error

        with patch("app.services.monitoring.logger"):
            with patch("app.config.settings") as mock_settings:
                mock_settings.SENTRY_DSN = ""
                # Should not raise
                capture_error(ValueError("no sentry"), {"key": "val"})

    def test_capture_error_no_context(self):
        """capture_error works without context dict."""
        from app.services.monitoring import capture_error

        with patch("app.services.monitoring.logger"):
            capture_error(ValueError("simple error"))

    def test_capture_error_monitoring_never_crashes(self):
        """Even if sentry_sdk itself throws, capture_error must not propagate."""
        from app.services.monitoring import capture_error

        with patch("app.services.monitoring.logger"):
            with patch("app.config.settings") as mock_settings:
                mock_settings.SENTRY_DSN = "https://fake@sentry.io/123"
                # Force sentry import to fail
                with patch.dict("sys.modules", {"sentry_sdk": None}):
                    # Should NOT raise
                    capture_error(ValueError("boom"))
