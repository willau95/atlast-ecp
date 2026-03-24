"""
Centralized error monitoring — Sentry capture + structured logging.
"""

import structlog

logger = structlog.get_logger()


def capture_error(error: Exception, context: dict | None = None) -> None:
    """Capture error to Sentry if configured. Always logs."""
    logger.error("error_captured", error=str(error), error_type=type(error).__name__, **(context or {}))
    try:
        from ..config import settings

        if settings.SENTRY_DSN:
            import sentry_sdk

            if context:
                with sentry_sdk.push_scope() as scope:
                    for k, v in context.items():
                        scope.set_extra(k, v)
                    sentry_sdk.capture_exception(error)
            else:
                sentry_sdk.capture_exception(error)
    except Exception:
        pass  # monitoring itself must never crash the app
