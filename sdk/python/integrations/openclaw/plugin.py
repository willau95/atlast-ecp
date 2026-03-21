"""
ECP — OpenClaw Plugin (tool_result_persist hook)

Passively records all OpenClaw tool results as ECP evidence.
Uses OpenClaw's tool_result_persist Plugin API.

Installation:
    openclaw plugin add atlast/ecp
    (or via join.md / skill.md one-sentence flow)

How it works:
    OpenClaw fires `on_tool_result` after every tool execution.
    This plugin intercepts that event, feeds into ECP Core,
    which handles hashing, chaining, signing, and local storage.
    Content NEVER leaves the device.
"""

import time
import threading
from typing import Optional

# ECP SDK imports (installed via pip install atlast-ecp)
try:
    from atlast_ecp.core import record_async, get_identity
    from atlast_ecp.batch import trigger_batch_upload
    _ECP_AVAILABLE = True
except ImportError:
    _ECP_AVAILABLE = False


# ─── OpenClaw Plugin Metadata ─────────────────────────────────────────────────

PLUGIN_NAME = "atlast-ecp"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "ATLAST ECP — passive evidence chain recording for OpenClaw agents"
PLUGIN_HOOKS = ["tool_result_persist", "session_end"]

# ─── Plugin State ─────────────────────────────────────────────────────────────

_session_records: list[str] = []
_lock = threading.Lock()


# ─── OpenClaw Hook: tool_result_persist ───────────────────────────────────────

def on_tool_result(
    tool_name: str,
    tool_input: dict,
    tool_result: str,
    latency_ms: Optional[int] = None,
    session_id: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Called by OpenClaw after every tool execution.
    Records the tool call as an ECP evidence record via core.record_async().
    Returns tool_result unchanged (pass-through).
    """
    if not _ECP_AVAILABLE:
        return tool_result

    try:
        in_content = {
            "tool": tool_name,
            "input": tool_input,
            "session_id": session_id,
        }

        record_async(
            input_content=in_content,
            output_content=str(tool_result),
            step_type="turn",
            model=kwargs.get("model"),
            tokens_in=kwargs.get("tokens_in"),
            tokens_out=kwargs.get("tokens_out"),
            latency_ms=latency_ms or 0,
        )
    except Exception:
        pass  # Fail-Open

    return tool_result


# ─── OpenClaw Hook: session_end ───────────────────────────────────────────────

def on_session_end(session_id: Optional[str] = None, **kwargs):
    """
    Called by OpenClaw when a session ends.
    Flushes pending records and triggers Merkle batch upload.
    """
    if not _ECP_AVAILABLE:
        return

    try:
        time.sleep(0.5)  # Give background threads time to finish
        trigger_batch_upload(flush=True)
    except Exception:
        pass  # Fail-Open


# ─── Plugin Registration (OpenClaw Plugin API) ────────────────────────────────

def register(openclaw_api):
    """
    Register ECP hooks with OpenClaw's Plugin API.
    Called automatically by: openclaw plugin add atlast/ecp
    """
    if not _ECP_AVAILABLE:
        print("⚠️  atlast-ecp SDK not found. Run: pip install atlast-ecp")
        return False

    try:
        openclaw_api.on("tool_result_persist", on_tool_result)
        openclaw_api.on("session_end", on_session_end)

        identity = get_identity()
        print(f"✅ ATLAST ECP active | Agent: {identity['did']}")
        print(f"   Evidence chain: .ecp/ (local, private)")
        print(f"   Register at your ECP server")
        return True

    except Exception as e:
        print(f"⚠️  ECP plugin registration failed (non-fatal): {e}")
        return False


def get_agent_did() -> Optional[str]:
    """Return the current agent's DID."""
    if not _ECP_AVAILABLE:
        return None
    return get_identity()["did"]


def get_session_record_ids() -> list[str]:
    """Return all record IDs created in this session."""
    with _lock:
        return list(_session_records)
