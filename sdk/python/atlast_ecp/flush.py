"""
ATLAST ECP — Buffer flush utility.

Flushes Claude Code hook buffers into ECP records.
Called by: dashboard server, CLI commands, hook script.

Design: any code path that READS records should flush stale buffers first,
so the user always sees complete data.
"""

import json
import logging
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

FLUSH_TIMEOUT_S = 300  # 5 minutes — Claude Code can think for minutes between tool calls


def flush_stale_buffers(timeout_s: int = FLUSH_TIMEOUT_S) -> int:
    """
    Flush all stale Claude Code hook buffers into ECP records.

    A buffer is "stale" if its last_update is older than timeout_s.
    Returns the number of records created.

    Safe to call frequently — no-op if no stale buffers exist.
    Fail-Open: never raises, never blocks.
    """
    from .storage import ECP_DIR

    buffer_dir = ECP_DIR / "hook_buffer"
    if not buffer_dir.exists():
        return 0

    flushed = 0
    now = time.time()

    for session_file in buffer_dir.glob("*.json"):
        try:
            buf = json.loads(session_file.read_text())
            last_update = buf.get("last_update", 0)

            if now - last_update < timeout_s:
                continue  # Not stale yet

            steps = buf.get("steps", [])
            if not steps:
                session_file.unlink(missing_ok=True)
                continue

            # Build aggregated record
            tool_names = [s.get("tool_name", "?") for s in steps]
            tool_summary = {}
            for name in tool_names:
                tool_summary[name] = tool_summary.get(name, 0) + 1
            summary_str = ", ".join(f"{name} x{count}" for name, count in tool_summary.items())

            # Try to read Claude Code transcript for real user message + agent response
            user_input = None
            agent_response = None
            transcript_path = buf.get("transcript_path", "")
            if transcript_path:
                try:
                    from pathlib import Path as _Path
                    tp = _Path(transcript_path)
                    if tp.exists():
                        entries = []
                        for tl in tp.read_text().splitlines():
                            if tl.strip():
                                try: entries.append(json.loads(tl))
                                except: pass
                        # Last real user message (text, not tool_result)
                        for e in reversed(entries):
                            if e.get("type") == "user":
                                c = e.get("message", {}).get("content", "")
                                if isinstance(c, str) and len(c) > 0:
                                    user_input = c[:1000]
                                    break
                        # Last assistant text response
                        for e in reversed(entries):
                            if e.get("type") == "assistant":
                                content = e.get("message", {}).get("content", [])
                                if isinstance(content, list):
                                    texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                                    if texts:
                                        agent_response = "\n".join(texts)[:3000]
                                        break
                except Exception:
                    pass

            # Fallback: use tool data if transcript not available
            first_input = user_input or ""
            if not first_input:
                for s in steps:
                    inp = s.get("tool_input_str", "")
                    if inp and len(inp) > 10:
                        first_input = inp[:500]
                        break

            last_output = agent_response or ""
            if not last_output:
                for s in reversed(steps):
                    out = s.get("tool_response", "")
                    if out and len(str(out)) > 5:
                        last_output = str(out)[:3000]
                        break

            total_latency = sum(s.get("duration_ms", 0) for s in steps)

            output_json = json.dumps({
                "final_response": last_output or f"Completed {len(steps)} actions: {summary_str}",
                "tool_calls_used": [
                    {"name": s.get("tool_name", "?"), "input": s.get("tool_input", {})}
                    for s in steps
                ],
                "steps": len(steps),
            }, ensure_ascii=False)

            from .core import record_minimal
            record_minimal(
                input_content=first_input or f"Claude Code session ({summary_str})",
                output_content=output_json,
                agent="claude-code",
                action="session",
                model="claude",
                latency_ms=total_latency,
            )

            session_file.unlink(missing_ok=True)
            flushed += 1
            _logger.debug("Flushed %d steps from %s", len(steps), session_file.name)

        except Exception as e:
            _logger.debug("flush_stale_buffers error on %s: %s", session_file, e)
            continue

    return flushed


def flush_all_buffers() -> int:
    """Force flush ALL buffers regardless of age. Used before displaying data."""
    return flush_stale_buffers(timeout_s=0)
