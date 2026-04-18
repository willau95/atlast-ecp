"""Transcript-driven recording scanner.

Core principle: the transcript file (~/.claude/projects/**/*.jsonl) is the
ground truth. ATLAST records are *derivatives* of it. Hooks are just
triggers — they don't decide what gets recorded. This module owns the
parsing and recording logic.

Benefits:
  1. 100% fidelity: `atlast sync` can reconstruct every turn byte-for-byte,
     regardless of whether hooks fired reliably.
  2. Extensibility: add a parser for Cursor / Cline / Aider transcripts and
     everything downstream works unchanged.
  3. Idempotent: same turn → same deterministic record_id → same vault
     content. Re-scanning never creates duplicates.

Turn model:
  - A "turn" is the span from one user message to the next user message
    (or end of transcript).
  - A turn is *finalized* when a successor user message exists — its content
    can no longer change.
  - A turn is *in progress* otherwise — its record may get rewritten on the
    next scan as more entries arrive.

Records:
  - record_id: deterministic per-turn. `recT` prefix distinguishes from
    legacy random-id records. Same (session_id, turn_start_ts, user_msg)
    always produces the same id.
  - On each scan, pending turns get their vault file overwritten with the
    latest state. Finalized turns get written once and then skipped.
"""
from __future__ import annotations
import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

# ─────────────────────────────────────────────────────────────
# Turn parsing
# ─────────────────────────────────────────────────────────────


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


_CLAUDE_INTERNAL_PREFIXES = (
    "<local-command-",       # CLI command stdout/stderr wrappers
    "<command-name>",         # slash-command markers
    "<command-message>",
    "<command-args>",
    "<system-reminder>",      # platform-injected reminders
    "<user-prompt-submit-hook>",
    "<ide_",                  # IDE-injected blocks
    "<function_",
    "[Request interrupted",   # Ctrl-C interrupt markers
)


def _is_internal_pseudo_msg(text: str) -> bool:
    """Claude Code embeds a lot of non-user content as user-type entries:
    slash command wrappers, stdout carriers, system reminders, interrupt
    markers. These look like user messages but aren't — counting them as
    turn boundaries produces garbage records like
    `input = "<local-command-stdout>Set model to ..."`.
    """
    if not text:
        return True
    s = text.lstrip()
    return s.startswith(_CLAUDE_INTERNAL_PREFIXES)


def _is_real_user_msg(entry: dict) -> bool:
    """True if this transcript entry is a genuine human-authored message.

    Excludes:
      - tool_result carriers (content blocks with no text)
      - Claude Code internal pseudo-messages (slash commands, stdout
        wrappers, system reminders, interrupt notices)
    """
    c = entry.get("message", {}).get("content", "")
    if isinstance(c, str):
        return bool(c.strip()) and not _is_internal_pseudo_msg(c)
    if isinstance(c, list):
        texts = [
            b.get("text", "")
            for b in c
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
        ]
        if not texts:
            return False
        # If every text block in this entry starts with a Claude Code
        # internal marker, treat it as a pseudo-message — not a real turn.
        return not all(_is_internal_pseudo_msg(t) for t in texts)
    return False


def _extract_user_text(entry: dict) -> str:
    """Extract the full user message text. No truncation."""
    c = entry.get("message", {}).get("content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = [
            b.get("text", "")
            for b in c
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "\n\n".join(p for p in parts if p)
    return str(c or "")


def _normalize_tool_result(raw: Any) -> str:
    """Convert a tool_result content field into a string verbatim.

    For list-form content: concatenate text blocks; for non-text blocks
    fall back to their JSON representation so we never lose data.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for b in raw:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", "") or "")
                elif "text" in b:
                    parts.append(b.get("text", "") or "")
                else:
                    parts.append(json.dumps(b, ensure_ascii=False))
            else:
                parts.append(str(b))
        return "\n".join(parts)
    return str(raw or "")


def read_transcript(path: str | Path) -> list[dict]:
    """Load all JSONL entries from a transcript file."""
    entries: list[dict] = []
    p = Path(path)
    if not p.exists():
        return entries
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                entries.append(json.loads(s))
            except Exception:
                continue
    except Exception:
        pass
    return entries


def extract_turns(entries: list[dict]) -> list[dict]:
    """Partition transcript entries into turns.

    Each turn is a dict:
      {
        "start_idx": int,        # index of the user message in entries
        "end_idx": int,          # exclusive; next user msg or len(entries)
        "user_ts": str,
        "user_text": str,
        "finalized": bool,       # True if a successor user msg exists
      }
    """
    turns: list[dict] = []
    user_indices: list[int] = [
        i for i, e in enumerate(entries)
        if e.get("type") == "user" and _is_real_user_msg(e)
    ]
    if not user_indices:
        return turns
    for k, start in enumerate(user_indices):
        end = user_indices[k + 1] if k + 1 < len(user_indices) else len(entries)
        ue = entries[start]
        turns.append({
            "start_idx": start,
            "end_idx": end,
            "user_ts": ue.get("timestamp"),
            "user_text": _extract_user_text(ue),
            "finalized": (k + 1 < len(user_indices)),
        })
    return turns


# ─────────────────────────────────────────────────────────────
# Timeline building (v3 schema) — byte-for-byte, zero truncation
# ─────────────────────────────────────────────────────────────


def build_timeline(entries: list[dict], start_idx: int, end_idx: int) -> dict:
    """Build a full-fidelity timeline for a turn spanning [start_idx+1, end_idx).

    Returns dict with timeline, totals, tool_names, last_model, first_ts, last_ts.
    """
    timeline: list[dict] = []
    tool_use_names: dict[str, str] = {}
    tool_names_all: list[str] = []
    msg_id_to_event: dict[str, dict] = {}

    totals = {
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "tool_calls": 0,
        "thinking_blocks": 0,
        "text_blocks": 0,
        "tool_results": 0,
        "context_length_peak": 0,
    }
    last_model: str | None = None
    first_ts: str | None = None
    last_ts: str | None = None
    seq = 0

    for i in range(start_idx + 1, end_idx):
        e = entries[i]
        etype = e.get("type", "")
        ts = e.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

        if etype == "assistant":
            msg = e.get("message", {})
            model = msg.get("model")
            if model and not last_model:
                last_model = model

            msg_id = msg.get("id") or f"__no_id_{i}"
            existing = msg_id_to_event.get(msg_id)

            usage = msg.get("usage", {}) or {}
            ti = int(usage.get("input_tokens", 0) or 0)
            to = int(usage.get("output_tokens", 0) or 0)
            cr = int(usage.get("cache_read_input_tokens", 0) or 0)
            cc = int(usage.get("cache_creation_input_tokens", 0) or 0)

            if existing is None:
                totals["llm_calls"] += 1
                totals["input_tokens"] += ti
                totals["output_tokens"] += to
                totals["cache_read_input_tokens"] += cr
                totals["cache_creation_input_tokens"] += cc
                ctx = ti + cr + cc
                if ctx > totals["context_length_peak"]:
                    totals["context_length_peak"] = ctx
                event = {
                    "seq": seq,
                    "ts": ts,
                    "type": "llm_call",
                    "message_id": msg_id,
                    "model": model,
                    "usage": {
                        "input_tokens": ti,
                        "output_tokens": to,
                        "cache_read_input_tokens": cr,
                        "cache_creation_input_tokens": cc,
                    },
                    "context_at_call": ctx,
                    "content": [],
                }
                timeline.append(event)
                msg_id_to_event[msg_id] = event
                seq += 1
            else:
                event = existing

            raw_content = msg.get("content", [])
            if isinstance(raw_content, list):
                for b in raw_content:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "thinking":
                        totals["thinking_blocks"] += 1
                        text = b.get("thinking", "") or b.get("text", "") or ""
                        sig = b.get("signature", "") or ""
                        event["content"].append({
                            "type": "thinking",
                            "text": text,
                            "signature": sig,
                            "redacted": (not text) and bool(sig),
                            "signature_bytes": len(sig),
                        })
                    elif bt == "text":
                        text = b.get("text", "") or ""
                        if text:
                            totals["text_blocks"] += 1
                            event["content"].append({"type": "text", "text": text})
                    elif bt == "tool_use":
                        tid = b.get("id", "")
                        name = b.get("name", "?")
                        inp = b.get("input", {})
                        tool_use_names[tid] = name
                        tool_names_all.append(name)
                        totals["tool_calls"] += 1
                        event["content"].append({
                            "type": "tool_use",
                            "id": tid,
                            "name": name,
                            "input": inp,  # full, verbatim
                        })
                    else:
                        # Preserve unknown blocks verbatim so we never lose data
                        event["content"].append(b)
            elif isinstance(raw_content, str) and raw_content:
                event["content"].append({"type": "text", "text": raw_content})

        elif etype == "tool_result":
            tid = e.get("tool_use_id", "")
            raw = e.get("content", "")
            content = _normalize_tool_result(raw)
            totals["tool_results"] += 1
            timeline.append({
                "seq": seq,
                "ts": ts,
                "type": "tool_result",
                "tool_use_id": tid,
                "tool_name": tool_use_names.get(tid),
                "content": content,
                "bytes": len(content.encode("utf-8")),
            })
            seq += 1

        elif etype == "user":
            # user entries can carry tool_results in their content list
            c = e.get("message", {}).get("content", "")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        tid = b.get("tool_use_id", "")
                        raw = b.get("content", "")
                        content = _normalize_tool_result(raw)
                        totals["tool_results"] += 1
                        timeline.append({
                            "seq": seq,
                            "ts": ts,
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "tool_name": tool_use_names.get(tid),
                            "content": content,
                            "bytes": len(content.encode("utf-8")),
                        })
                        seq += 1

    return {
        "timeline": timeline,
        "totals": totals,
        "tool_names": tool_names_all,
        "last_model": last_model,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def build_narrative(timeline: list[dict]) -> str:
    """Readable agent narrative derived from timeline (for `output` field).

    Text blocks + short tool call headers + short tool result previews.
    The authoritative data stays in timeline — this is just for list views.
    """
    parts: list[str] = []
    for ev in timeline:
        if ev["type"] == "llm_call":
            for b in ev.get("content", []):
                t = b.get("type")
                if t == "text":
                    text = b.get("text", "")
                    if text:
                        parts.append(text)
                elif t == "tool_use":
                    name = b.get("name", "?")
                    inp = b.get("input", {})
                    preview = ""
                    if isinstance(inp, dict):
                        for k in ("command", "file_path", "pattern", "url", "query"):
                            if k in inp:
                                preview = str(inp[k])
                                break
                        if not preview:
                            preview = json.dumps(inp, ensure_ascii=False)
                    parts.append(f"[{name}] {preview}")
        elif ev["type"] == "tool_result":
            content = ev.get("content", "")
            preview = content[:400].replace("\n", " ")
            if preview:
                parts.append(f"→ {preview}")
    return "\n\n".join(parts) if parts else "(no response)"


# ─────────────────────────────────────────────────────────────
# Deterministic record id
# ─────────────────────────────────────────────────────────────


def deterministic_record_id(session_id: str, turn_start_ts: str, user_text: str) -> str:
    """Same (session_id, turn_start_ts, user_text) always yields the same id.

    Prefix recT_ distinguishes transcript-sourced records from legacy rec_*.
    """
    h = hashlib.sha256()
    h.update((session_id or "").encode("utf-8"))
    h.update(b"|")
    h.update((turn_start_ts or "").encode("utf-8"))
    h.update(b"|")
    h.update((user_text or "").encode("utf-8"))
    return "recT_" + h.hexdigest()[:16]


# ─────────────────────────────────────────────────────────────
# Agent-name derivation (Claude Code convention)
# ─────────────────────────────────────────────────────────────


def derive_agent_name(transcript_path: Path) -> str:
    try:
        project_dir = transcript_path.parent.name
        parts = [p for p in project_dir.split("-") if p and p != "Users"]
        for i, p in enumerate(parts):
            if p in ("Desktop", "Documents", "Projects", "repos", "code", "src", "home"):
                return "-".join(parts[i + 1:]) or "claude-code"
        return parts[-1] if parts else "claude-code"
    except Exception:
        return "claude-code"


# ─────────────────────────────────────────────────────────────
# Subagents
# ─────────────────────────────────────────────────────────────


def find_subagents_in_turn(transcript_path: Path, turn_start_ts: str | None,
                            turn_end_ts: str | None) -> list[dict]:
    """Find subagent JSONL files whose first entry falls within the turn window.

    Returns a list of {path, agent_id, agent_type, description, first_ts}.
    """
    if not turn_start_ts:
        return []
    session_dir = transcript_path.parent / transcript_path.stem
    sub_dir = session_dir / "subagents"
    if not sub_dir.exists():
        return []

    start_dt = _parse_iso(turn_start_ts)
    end_dt = _parse_iso(turn_end_ts) if turn_end_ts else None
    out: list[dict] = []
    for sa_file in sorted(sub_dir.glob("agent-*.jsonl")):
        try:
            # Only read first line to get first_ts quickly
            with sa_file.open("r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            if not first_line:
                continue
            first_entry = json.loads(first_line)
        except Exception:
            continue
        first_ts_str = first_entry.get("timestamp")
        first_dt = _parse_iso(first_ts_str)
        if start_dt and first_dt and first_dt < start_dt:
            continue
        if end_dt and first_dt and first_dt > end_dt:
            continue

        # Pull meta
        meta_file = sa_file.parent / (sa_file.stem + ".meta.json")
        agent_type = description = None
        if meta_file.exists():
            try:
                m = json.loads(meta_file.read_text())
                agent_type = m.get("agentType")
                description = m.get("description")
            except Exception:
                pass

        out.append({
            "path": sa_file,
            "agent_id": sa_file.stem.replace("agent-", ""),
            "agent_type": agent_type,
            "description": description,
            "first_ts": first_ts_str,
        })
    return out


# ─────────────────────────────────────────────────────────────
# Subagent timeline builder — same byte-level fidelity
# ─────────────────────────────────────────────────────────────


def build_subagent_vault(sa_path: Path) -> dict | None:
    """Build a v3 vault_extra payload for a single subagent JSONL file."""
    entries = read_transcript(sa_path)
    if len(entries) < 2:
        return None

    # First user message = subagent's prompt
    prompt = None
    prompt_idx = -1
    for i, e in enumerate(entries):
        if e.get("type") == "user" and _is_real_user_msg(e):
            prompt = _extract_user_text(e)
            prompt_idx = i
            break
    if not prompt or prompt_idx < 0:
        return None

    built = build_timeline(entries, prompt_idx, len(entries))
    return {
        "prompt": prompt,
        "timeline": built["timeline"],
        "totals": built["totals"],
        "tool_names": built["tool_names"],
        "last_model": built["last_model"],
        "first_ts": built["first_ts"],
        "last_ts": built["last_ts"],
    }


# ─────────────────────────────────────────────────────────────
# Main scan + record
# ─────────────────────────────────────────────────────────────


def scan_and_record(transcript_path: str | Path, *, only_finalized: bool = False,
                    log: Any = None) -> dict:
    """Parse a session transcript and upsert every turn as an ECP record.

    Args:
        transcript_path: path to the session .jsonl file.
        only_finalized: if True, skip the current in-progress turn; write only
            turns that have a successor user message.
        log: optional callable(str) for progress messages.

    Returns a summary dict.
    """
    from .core import record_minimal_v2
    from .storage import ECP_DIR

    def _l(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass

    tpath = Path(transcript_path)
    session_id = tpath.stem
    entries = read_transcript(tpath)
    if not entries:
        return {"session_id": session_id, "turns_scanned": 0, "turns_recorded": 0}

    agent_name = derive_agent_name(tpath)
    turns = extract_turns(entries)
    _l(f"Session {session_id[:12]}: {len(entries)} entries, {len(turns)} turns")

    recorded = 0
    skipped_finalized = 0
    skipped_in_progress = 0
    subagent_recorded = 0

    vault_dir = ECP_DIR / "vault"

    for idx, turn in enumerate(turns):
        if only_finalized and not turn["finalized"]:
            skipped_in_progress += 1
            continue

        rec_id = deterministic_record_id(session_id, turn["user_ts"] or "",
                                         turn["user_text"])

        # If this turn is already finalized AND the existing vault says finalized,
        # we can safely skip — content can never change.
        vault_path = vault_dir / f"{rec_id}.json"
        if turn["finalized"] and vault_path.exists():
            try:
                existing_vault = json.loads(vault_path.read_text())
                if existing_vault.get("finalized") is True:
                    skipped_finalized += 1
                    continue
            except Exception:
                pass  # fall through and rewrite

        built = build_timeline(entries, turn["start_idx"], turn["end_idx"])
        turn_end_ts = built["last_ts"] or turn["user_ts"]

        # Subagents that belong to this turn
        sub_info = find_subagents_in_turn(tpath, turn["user_ts"], turn_end_ts)
        sub_records_data: list[dict] = []
        for sa in sub_info:
            sa_vault = build_subagent_vault(sa["path"])
            if sa_vault:
                sa_vault.update({
                    "agent_id": sa["agent_id"],
                    "agent_type": sa["agent_type"],
                    "description": sa["description"],
                })
                sub_records_data.append(sa_vault)

        sub_totals = {
            "count": len(sub_records_data),
            "llm_calls": sum(s["totals"]["llm_calls"] for s in sub_records_data),
            "input_tokens": sum(s["totals"]["input_tokens"] for s in sub_records_data),
            "output_tokens": sum(s["totals"]["output_tokens"] for s in sub_records_data),
            "cache_read_input_tokens": sum(s["totals"]["cache_read_input_tokens"] for s in sub_records_data),
            "cache_creation_input_tokens": sum(s["totals"]["cache_creation_input_tokens"] for s in sub_records_data),
            "tool_calls": sum(s["totals"]["tool_calls"] for s in sub_records_data),
            "thinking_blocks": sum(s["totals"]["thinking_blocks"] for s in sub_records_data),
        }

        # Compute latency from timestamps
        start_dt = _parse_iso(turn["user_ts"])
        end_dt = _parse_iso(turn_end_ts)
        latency_ms = 0
        if start_dt and end_dt:
            latency_ms = max(0, int((end_dt - start_dt).total_seconds() * 1000))

        narrative = build_narrative(built["timeline"])

        vault_extra = {
            "vault_version": 3,
            "schema": "atlast.turn.v3",
            "framework": "claude-code",
            "session_id": session_id,
            "turn_index": idx,
            "turn_start_ts": turn["user_ts"],
            "turn_end_ts": turn_end_ts,
            "finalized": turn["finalized"],
            "model": built["last_model"],
            "latency_ms": latency_ms,
            "totals": built["totals"],
            "timeline": built["timeline"],
            "tool_names": built["tool_names"],
            "subagent_count": len(sub_records_data),
            "subagent_ids": [s["agent_id"] for s in sub_records_data],
            "subagent_totals": sub_totals,
            "source": {
                "transcript_path": str(tpath),
                "entries_scanned": turn["end_idx"] - turn["start_idx"] - 1,
                "scanned_at": datetime.utcnow().isoformat() + "Z",
            },
        }

        # Write the record. record_minimal_v2 handles index + vault in one call.
        try:
            record_minimal_v2(
                input_content=turn["user_text"],
                output_content=narrative,
                agent=agent_name,
                action="conversation",
                model=built["last_model"] or "claude",
                latency_ms=latency_ms,
                tokens_in=built["totals"]["input_tokens"] or None,
                tokens_out=built["totals"]["output_tokens"] or None,
                session_id=session_id,
                thread_id=session_id,
                vault_extra=vault_extra,
                record_id=rec_id,
            )
            recorded += 1
            _l(f"  turn[{idx}] {'FINAL' if turn['finalized'] else 'in-progress'} "
               f"id={rec_id} calls={built['totals']['llm_calls']} "
               f"tools={built['totals']['tool_calls']} subs={len(sub_records_data)}")
        except Exception as e:
            _l(f"  ERROR turn[{idx}]: {e}")
            continue

        # Record subagents too (each as its own record)
        for sa in sub_records_data:
            sa_rec_id = deterministic_record_id(
                session_id, sa["first_ts"] or "", sa["prompt"]
            )
            # Skip if already finalized — subagents finalize once the parent turn does
            sa_vault_path = vault_dir / f"{sa_rec_id}.json"
            if turn["finalized"] and sa_vault_path.exists():
                try:
                    existing = json.loads(sa_vault_path.read_text())
                    if existing.get("finalized") is True:
                        continue
                except Exception:
                    pass

            sa_narrative = build_narrative(sa["timeline"])
            sa_vault_extra = {
                "vault_version": 3,
                "schema": "atlast.turn.v3",
                "framework": "claude-code",
                "session_id": session_id,
                "parent_record_id": rec_id,
                "parent_agent": agent_name,
                "subagent_id": sa["agent_id"],
                "subagent_type": sa["agent_type"],
                "description": sa["description"],
                "finalized": turn["finalized"],
                "model": sa["last_model"],
                "turn_start_ts": sa["first_ts"],
                "turn_end_ts": sa["last_ts"],
                "totals": sa["totals"],
                "timeline": sa["timeline"],
                "tool_names": sa["tool_names"],
                "source": {
                    "subagent_path": str(sa["path"]) if isinstance(sa.get("path"), Path) else None,
                },
            }
            try:
                record_minimal_v2(
                    input_content=sa["prompt"],
                    output_content=sa_narrative,
                    agent=f"{agent_name}/subagent",
                    action="subagent",
                    model=sa["last_model"] or built["last_model"] or "claude",
                    latency_ms=0,
                    tokens_in=sa["totals"]["input_tokens"] or None,
                    tokens_out=sa["totals"]["output_tokens"] or None,
                    session_id=session_id,
                    thread_id=session_id,
                    vault_extra=sa_vault_extra,
                    record_id=sa_rec_id,
                )
                subagent_recorded += 1
            except Exception as e:
                _l(f"    ERROR subagent {sa['agent_id'][:12]}: {e}")

    return {
        "session_id": session_id,
        "turns_scanned": len(turns),
        "turns_recorded": recorded,
        "turns_skipped_finalized": skipped_finalized,
        "turns_skipped_in_progress": skipped_in_progress,
        "subagents_recorded": subagent_recorded,
    }


def scan_all_sessions(claude_projects_dir: str | Path | None = None,
                       log: Any = None) -> list[dict]:
    """Walk every Claude Code project transcript and upsert records.

    Skips transcripts whose on-disk mtime hasn't changed since last scan
    (tracked via a small manifest under ~/.ecp/transcript_scan_manifest.json).
    """
    from .storage import ECP_DIR

    if claude_projects_dir is None:
        claude_projects_dir = Path.home() / ".claude" / "projects"
    pdir = Path(claude_projects_dir)
    if not pdir.exists():
        return []

    manifest_path = ECP_DIR / "transcript_scan_manifest.json"
    manifest: dict[str, dict] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            manifest = {}

    results: list[dict] = []
    for tpath in pdir.rglob("*.jsonl"):
        if "/subagents/" in str(tpath) or tpath.name == "history.jsonl":
            continue
        try:
            mtime = tpath.stat().st_mtime
            size = tpath.stat().st_size
        except Exception:
            continue
        key = str(tpath)
        prev = manifest.get(key, {})
        # Only skip if both mtime and size unchanged (transcripts append-only,
        # so size is a reliable growth signal).
        if prev.get("mtime") == mtime and prev.get("size") == size:
            continue

        summary = scan_and_record(tpath, log=log)
        results.append(summary)
        manifest[key] = {"mtime": mtime, "size": size, "last_scan": datetime.utcnow().isoformat() + "Z"}

    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2))
    except Exception:
        pass

    return results
