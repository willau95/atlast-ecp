"""
ATLAST ECP — Scanner Service (DEPRECATED)

Scanner has been removed. It generated fake data by scraping session logs
instead of capturing real API calls. Use `atlast proxy` instead.

All functions return no-op results for backward compatibility.
"""


def detect_openclaw_agents() -> list[dict]:
    """Deprecated — returns empty list."""
    return []


def setup_scanner_service() -> dict:
    """Deprecated — returns error status."""
    return {"status": "error", "message": "Scanner deprecated. Use: atlast proxy"}


def get_scanner_status() -> dict:
    """Deprecated — returns not-running."""
    return {"running": False, "method": "deprecated"}
