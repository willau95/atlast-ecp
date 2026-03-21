#!/usr/bin/env python3
"""
ATLAST ECP — OpenClaw Session Log Scanner

Scans OpenClaw agent session logs (.jsonl) and creates ECP records
for each LLM interaction. Designed to run as a cron job or one-off scan.

Usage:
    python -m atlast_ecp.openclaw_scanner ~/.openclaw-david-bazi
    python -m atlast_ecp.openclaw_scanner ~/.openclaw-david-bazi --agent-name "david-bazi" --watch
"""

import json
import os
import sys
import time
import hashlib
from pathlib import Path
from typing import Optional

from .core import record
from .identity import get_or_create_identity
from .batch import run_batch


def scan_session_file(jsonl_path: str, since_ts: Optional[str] = None) -> list[dict]:
    """
    Parse an OpenClaw session .jsonl file and extract LLM interactions.
    Returns list of {input, output, model, tokens_in, tokens_out, latency_ms, timestamp}.
    """
    interactions = []
    messages = []

    with open(jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            messages.append(entry)

    # Extract pairs: user message → assistant response
    pending_user = None
    for entry in messages:
        ts = entry.get("timestamp", "")
        if since_ts and ts <= since_ts:
            continue

        if entry.get("type") == "message":
            msg = entry.get("message", {})
            role = msg.get("role", "")

            if role == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", "") for c in content if isinstance(c, dict)
                    )
                pending_user = {
                    "content": str(content)[:2000],
                    "timestamp": ts,
                }

            elif role == "assistant" and pending_user:
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Extract text parts, skip thinking blocks
                    parts = []
                    for c in content:
                        if isinstance(c, dict):
                            if c.get("type") == "text":
                                parts.append(c.get("text", ""))
                            elif c.get("type") == "tool_use":
                                parts.append(f"[tool:{c.get('name','')}]")
                    content = " ".join(parts)

                interactions.append({
                    "input": pending_user["content"],
                    "output": str(content)[:2000],
                    "timestamp": ts,
                    "input_ts": pending_user["timestamp"],
                })
                pending_user = None

        # Extract model/usage from custom cache-ttl entries
        elif entry.get("type") == "custom" and entry.get("customType") == "openclaw.cache-ttl":
            data = entry.get("data", {})
            model_id = data.get("modelId", "")
            # Attach model info to the most recent interaction
            if interactions and not interactions[-1].get("model"):
                interactions[-1]["model"] = model_id

        # Extract usage from response metadata
        elif entry.get("type") == "custom" and "usage" in str(entry.get("data", {})):
            data = entry.get("data", {})
            usage = data.get("usage", {})
            if interactions and usage:
                interactions[-1]["tokens_in"] = usage.get("input_tokens", 0)
                interactions[-1]["tokens_out"] = usage.get("output_tokens", 0)

    # Compute latency from timestamps
    for ix in interactions:
        try:
            from datetime import datetime
            t1 = datetime.fromisoformat(ix["input_ts"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(ix["timestamp"].replace("Z", "+00:00"))
            ix["latency_ms"] = int((t2 - t1).total_seconds() * 1000)
        except Exception:
            ix["latency_ms"] = 0

    return interactions


def _set_agent_ecp_dir(agent_name: str):
    """Set ECP storage directory per agent for independent DIDs."""
    ecp_dir = os.path.expanduser(f"~/.ecp/agents/{agent_name}")
    os.environ["ATLAST_ECP_DIR"] = ecp_dir
    # Reload storage paths
    from . import storage
    storage.ECP_DIR = Path(ecp_dir)
    storage.RECORDS_DIR = storage.ECP_DIR / "records"
    storage.LOCAL_DIR = storage.ECP_DIR / "local"
    storage.INDEX_FILE = storage.ECP_DIR / "index.json"
    storage.QUEUE_FILE = storage.ECP_DIR / "upload_queue.jsonl"
    storage.init_storage()
    # Also reset identity cache so each agent gets its own DID
    from . import identity
    identity.IDENTITY_FILE = storage.ECP_DIR / "identity.json"


def scan_openclaw_agent(
    agent_dir: str,
    agent_name: Optional[str] = None,
    since_ts: Optional[str] = None,
) -> dict:
    """
    Scan all session files for an OpenClaw agent directory.
    Creates ECP records for each LLM interaction.
    Returns summary stats.
    """
    agent_path = Path(agent_dir)
    sessions_dir = agent_path / "agents" / "main" / "sessions"

    if not sessions_dir.exists():
        print(f"No sessions directory: {sessions_dir}")
        return {"error": "no sessions dir", "records": 0}

    # Read agent name from IDENTITY.md if not provided
    if not agent_name:
        identity_file = agent_path / "workspace" / "IDENTITY.md"
        if identity_file.exists():
            text = identity_file.read_text().replace("\\n", "\n")
            for line in text.splitlines():
                if "Name:" in line and "**" in line:
                    agent_name = line.split("Name:")[-1].strip().strip("*").strip()
                    if agent_name:
                        break
        if not agent_name:
            agent_name = agent_path.name.replace(".openclaw-", "")

    # Set per-agent ECP directory (each agent gets its own DID)
    safe_name = agent_name.replace(" ", "-").replace("/", "-")[:50]
    _set_agent_ecp_dir(safe_name)

    # State file to track what we've already scanned
    state_file = Path(os.path.expanduser("~/.ecp")) / f"openclaw_scan_{hashlib.md5(agent_dir.encode()).hexdigest()[:8]}.json"
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except Exception:
            pass

    total_new = 0
    total_skipped = 0

    for jsonl_file in sorted(sessions_dir.glob("*.jsonl")):
        file_key = jsonl_file.name
        last_ts = state.get(file_key, since_ts)

        interactions = scan_session_file(str(jsonl_file), since_ts=last_ts)
        if not interactions:
            continue

        for ix in interactions:
            rid = record(
                input_content=ix["input"],
                output_content=ix["output"],
                model=ix.get("model", "unknown"),
                tokens_in=ix.get("tokens_in", 0),
                tokens_out=ix.get("tokens_out", 0),
                latency_ms=ix.get("latency_ms", 0),
            )
            if rid:
                total_new += 1
            else:
                total_skipped += 1

        # Update state with latest timestamp
        if interactions:
            state[file_key] = interactions[-1]["timestamp"]

    # Save state
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state))

    return {
        "agent_name": agent_name,
        "agent_dir": agent_dir,
        "new_records": total_new,
        "skipped": total_skipped,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scan OpenClaw agent sessions for ECP recording")
    parser.add_argument("agent_dir", help="OpenClaw agent directory (e.g. ~/.openclaw-david-bazi)")
    parser.add_argument("--agent-name", help="Override agent name")
    parser.add_argument("--batch", action="store_true", help="Run batch upload after scan")
    parser.add_argument("--watch", action="store_true", help="Watch mode: scan every 60s")
    parser.add_argument("--interval", type=int, default=60, help="Watch interval in seconds")
    args = parser.parse_args()

    agent_dir = os.path.expanduser(args.agent_dir)
    print(f"Scanning: {agent_dir}")

    while True:
        result = scan_openclaw_agent(agent_dir, agent_name=args.agent_name)
        did = get_or_create_identity()["did"]
        print(f"[{time.strftime('%H:%M:%S')}] {result['agent_name']} ({did}): {result['new_records']} new records")

        if args.batch and result["new_records"] > 0:
            print("  Running batch upload...")
            run_batch()
            print("  Batch complete.")

        if not args.watch:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
