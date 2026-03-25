"""
ECP — Claude Code Plugin (Hook-based passive recording)

Hooks into Claude Code's PreToolUse and PostToolUse events
to passively record all tool calls as ECP evidence.

Installation:
    python -m atlast_ecp.install_claude
    (or via join.md / skill.md)

How it works:
    PreToolUse  → capture tool name + input + start time
    PostToolUse → feed into ECP Core (hash, chain, sign, store)
    Content NEVER leaves the device.
"""

import json
import sys
import time
import threading
from pathlib import Path

# In-flight tracking (PreToolUse → PostToolUse correlation)
_in_flight: dict[str, dict] = {}
_lock = threading.Lock()


def _get_core():
    """Lazy import ECP Core (fails silently if not installed)."""
    try:
        from atlast_ecp.core import record_async, get_identity
        from atlast_ecp.record import hash_content
        return {
            "record_async": record_async,
            "get_identity": get_identity,
            "hash_content": hash_content,
        }
    except ImportError:
        return None


# ─── Claude Code Hook Entry Points ───────────────────────────────────────────

def pre_tool_use(tool_name: str, tool_input: dict) -> dict:
    """
    Called by Claude Code BEFORE a tool is executed.
    Records start time for latency tracking.
    Returns tool_input unchanged (pass-through).
    """
    call_id = f"{tool_name}_{time.time_ns()}"

    try:
        in_content = {"tool": tool_name, "input": tool_input}
        with _lock:
            _in_flight[call_id] = {
                "tool_name": tool_name,
                "in_content": in_content,
                "t_start": time.time(),
            }
    except Exception:
        pass  # Fail-Open

    return {**tool_input, "__ecp_call_id": call_id}


def post_tool_use(tool_name: str, tool_input: dict, tool_result: str) -> str:
    """
    Called by Claude Code AFTER a tool is executed.
    Feeds into ECP Core for recording.
    Returns tool_result unchanged (pass-through).
    """
    try:
        core = _get_core()
        if not core:
            return tool_result

        call_id = tool_input.pop("__ecp_call_id", None)

        with _lock:
            in_flight = _in_flight.pop(call_id, None) if call_id else None

        if not in_flight:
            in_flight = {
                "tool_name": tool_name,
                "in_content": {"tool": tool_name, "input": tool_input},
                "t_start": time.time(),
            }

        latency_ms = int((time.time() - in_flight["t_start"]) * 1000)

        core["record_async"](
            input_content=in_flight["in_content"],
            output_content=tool_result,
            step_type="tool_call",
            latency_ms=latency_ms,
        )

    except Exception:
        pass  # Fail-Open

    return tool_result
