"""
ECP Core — the single unified interface for all adapters.

Every adapter (wrap, OTel, OpenClaw Hook, Claude Code Plugin)
calls core.record(). This is the "MCP" of ECP — one door, many paths in.

Design: stateful singleton managing identity, chain, and async recording.
Thread-safe. Fail-Open. Never raises.
"""

import threading
import time
from typing import Any, Optional

from .identity import get_or_create_identity, sign
from .record import create_record, create_minimal_record, record_to_dict, hash_content, ECPRecord
from .storage import save_record
from .signals import detect_flags


class _ECPState:
    """Global ECP state. Thread-safe singleton."""

    def __init__(self):
        self._identity = None
        self._last_record: Optional[ECPRecord] = None
        self._call_hashes: dict[str, int] = {}  # in_hash → count (retry detection)
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def identity(self) -> dict:
        if self._identity is None:
            self._identity = get_or_create_identity()
        return self._identity

    def get_and_set_last_record(self, new_record: ECPRecord) -> Optional[ECPRecord]:
        """Atomically get previous and set new last_record."""
        with self._lock:
            prev = self._last_record
            self._last_record = new_record
            return prev

    def check_retry(self, in_hash: str) -> bool:
        """Check if this input hash was seen before (retry detection)."""
        with self._lock:
            count = self._call_hashes.get(in_hash, 0)
            self._call_hashes[in_hash] = count + 1
            return count > 0

    def reset(self):
        """Reset state (for testing)."""
        with self._lock:
            self._last_record = None
            self._call_hashes = {}


# Global singleton
_state = _ECPState()


def record(
    input_content: Any,
    output_content: Any,
    step_type: str = "llm_call",
    model: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: int = 0,
    is_retry: Optional[bool] = None,
    local_summary: Optional[str] = None,
    parent_agent: Optional[str] = None,
) -> Optional[str]:
    """
    ECP's single unified interface.

    All adapters call this function. It:
      1. Hashes input/output (content never leaves device)
      2. Detects behavioral flags passively
      3. Chains to previous record
      4. Signs with ed25519
      5. Saves to local .ecp/
      6. Returns record_id (or None on failure — Fail-Open)

    Thread-safe. Async-friendly (call from background thread).
    NEVER raises — all errors are swallowed (Fail-Open).
    """
    try:
        identity = _state.identity

        # Extract text for flag detection
        out_text = _extract_text(output_content)

        # Auto-detect retry if not explicitly set
        if is_retry is None:
            in_hash = hash_content(input_content)
            is_retry = _state.check_retry(in_hash)

        # Passive behavioral flag detection
        flags = detect_flags(out_text, is_retry=is_retry, latency_ms=latency_ms)

        # Create record (chained to previous)
        rec = create_record(
            agent_did=identity["did"],
            step_type=step_type,
            in_content=input_content,
            out_content=output_content,
            identity=identity,
            prev_record=_state._last_record,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            flags=flags,
            parent_agent=parent_agent,
        )

        # Save locally
        rec_dict = record_to_dict(rec)
        save_record(rec_dict, local_summary=local_summary)

        # Update chain state
        _state.get_and_set_last_record(rec)

        return rec.id

    except Exception:
        # Fail-Open: recording failure NEVER affects the caller
        return None


def record_async(
    input_content: Any,
    output_content: Any,
    **kwargs,
) -> None:
    """
    Fire-and-forget version of record().
    Runs in a background daemon thread. Never blocks. Never raises.
    """
    t = threading.Thread(
        target=record,
        args=(input_content, output_content),
        kwargs=kwargs,
        daemon=True,
    )
    t.start()


def get_identity() -> dict:
    """Get the current agent's identity (DID + keys)."""
    return _state.identity


def reset():
    """Reset ECP state (for testing only)."""
    _state.reset()


def record_minimal(
    input_content: Any,
    output_content: Any,
    agent: str = "default",
    action: str = "llm_call",
    model: Optional[str] = None,
    latency_ms: int = 0,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
) -> Optional[str]:
    """
    Minimal ECP recording. No identity, no chain, no signature.
    Just hash + detect flags + save locally.

    The simplest possible ECP record. Use this when you don't need
    cryptographic identity or chain integrity — just evidence logging.

    Returns record_id (or None on failure — Fail-Open).
    """
    try:
        out_text = _extract_text(output_content)
        flags = detect_flags(out_text, latency_ms=latency_ms)

        meta = {}
        if model:
            meta["model"] = model
        if latency_ms:
            meta["latency_ms"] = latency_ms
        if tokens_in is not None:
            meta["tokens_in"] = tokens_in
        if tokens_out is not None:
            meta["tokens_out"] = tokens_out
        if flags:
            meta["flags"] = flags

        rec = create_minimal_record(
            agent=agent,
            action=action,
            in_content=input_content,
            out_content=output_content,
            meta=meta if meta else None,
        )
        save_record(rec)
        return rec["id"]
    except Exception:
        return None


def record_minimal_async(
    input_content: Any,
    output_content: Any,
    **kwargs,
) -> None:
    """Fire-and-forget version of record_minimal()."""
    t = threading.Thread(
        target=record_minimal,
        args=(input_content, output_content),
        kwargs=kwargs,
        daemon=True,
    )
    t.start()


def _is_anonymous() -> bool:
    """Check if anonymous mode is enabled (no identity auto-creation)."""
    import os
    return os.environ.get("ATLAST_ANONYMOUS", "").strip() in ("1", "true", "yes")


def _extract_text(content: Any) -> str:
    """Extract plain text from various response formats."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif "text" in item:
                    parts.append(item["text"])
        return " ".join(parts)
    if hasattr(content, "text"):
        return content.text
    return str(content)
