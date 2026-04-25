"""
Vault v4 — wire-level evidence (raw HTTP request/response bytes).

claude-trace inspired: store the byte-for-byte HTTP transcript of every LLM
API call, separate from the higher-level "record" abstraction. A single ECP
record may aggregate multiple API roundtrips (e.g. tool-use loops) — each
roundtrip becomes its own wire entry, and the record references them by id.

On-disk layout:
    ~/.ecp/vault/wire/<wire_id>/
        meta.json       — schema v4, sanitized headers, hashes, timing
        request.json    — raw request body bytes (verbatim)
        response.sse    — raw SSE stream bytes (if streaming)
        response.json   — raw response body bytes (if non-streaming)

A wire_id is deterministic from (request_body || response_body || timestamp)
so identical roundtrips dedupe.

Threat model:
- Wire data is plaintext (system prompts, tool args, model outputs). Same
  sensitivity as identity.json. Files written 0600, dirs 0700.
- Authorization-style headers redacted at write time (claude-trace pattern:
  first6 + "..." + last4).
- Set ATLAST_WIRE_DISABLE=1 to skip wire capture entirely.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

WIRE_VERSION = 4
WIRE_SCHEMA = "atlast.wire.v4"
SAFE_FILE_PERMS = 0o600
SAFE_DIR_PERMS = 0o700

# Header substrings that mark a value as sensitive. Match is substring-on-lowercase
# so "anthropic-auth-token" and "x-api-key" both hit.
_SENSITIVE_HEADER_MARKERS = (
    "authorization",
    "api-key",
    "auth-token",
    "cookie",
    "session-token",
    "access-token",
    "bearer",
    "proxy-authorization",
    "secret",
)


def is_disabled() -> bool:
    """Operator opt-out: ATLAST_WIRE_DISABLE=1 turns off all wire capture."""
    return os.environ.get("ATLAST_WIRE_DISABLE", "").strip().lower() in ("1", "true", "yes")


def _redact(value: str) -> str:
    """first6 + '...' + last4 if long enough, otherwise opaque."""
    if not isinstance(value, str):
        return "***"
    if len(value) > 14:
        return f"{value[:6]}...{value[-4:]}"
    if len(value) > 4:
        return f"{value[:2]}...{value[-2:]}"
    return "***"


def redact_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Return a copy of headers with sensitive values redacted to first6+last4."""
    if not headers:
        return {}
    out: Dict[str, str] = {}
    for k, v in headers.items():
        lk = (k or "").lower()
        if any(marker in lk for marker in _SENSITIVE_HEADER_MARKERS):
            out[k] = _redact(str(v))
        else:
            out[k] = str(v) if v is not None else ""
    return out


def _wire_root(ecp_dir: Optional[Path] = None) -> Path:
    base = Path(ecp_dir) if ecp_dir else (Path.home() / ".ecp")
    return base / "vault" / "wire"


def _wire_dir(wire_id: str, ecp_dir: Optional[Path] = None) -> Path:
    return _wire_root(ecp_dir) / wire_id


def _sha256_hex(b: Optional[bytes]) -> Optional[str]:
    if not b:
        return None
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _stable_sha_of_json(obj: Any) -> Optional[str]:
    """sha256 of canonical-json serialization (sort_keys, ensure_ascii)."""
    if obj is None:
        return None
    try:
        canon = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return _sha256_hex(canon.encode("utf-8"))
    except Exception:
        return None


def make_wire_id(request_body: Optional[bytes], response_body: Optional[bytes],
                 started_at: float = 0.0) -> str:
    """Deterministic wire_id from req+resp+timestamp. 16 hex chars after `wire_`."""
    h = hashlib.sha256()
    h.update(request_body or b"")
    h.update(b"|")
    h.update(response_body or b"")
    h.update(b"|")
    h.update(str(int(started_at * 1000)).encode("ascii"))
    return f"wire_{h.hexdigest()[:16]}"


def _safe_chmod(p: Path, mode: int) -> None:
    try:
        os.chmod(p, mode)
    except Exception:
        pass


def _atomic_write_bytes(path: Path, data: bytes, mode: int = SAFE_FILE_PERMS) -> None:
    """Write atomically: tmp file in same dir, then rename. Set perms after."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    _safe_chmod(tmp, mode)
    os.replace(tmp, path)


def _atomic_write_text(path: Path, data: str, mode: int = SAFE_FILE_PERMS) -> None:
    _atomic_write_bytes(path, data.encode("utf-8"), mode)


def save_wire(
    *,
    request_url: str = "",
    request_method: str = "POST",
    request_headers: Optional[Dict[str, str]] = None,
    request_body_bytes: Optional[bytes] = None,
    response_status: int = 0,
    response_headers: Optional[Dict[str, str]] = None,
    response_body_bytes: Optional[bytes] = None,
    response_content_type: str = "",
    started_at: float = 0.0,
    finished_at: float = 0.0,
    provider: str = "",
    error: Optional[str] = None,
    ecp_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Persist a single HTTP roundtrip as Vault v4 evidence.

    Returns a small dict suitable for embedding in record.meta.wire_summary,
    plus the canonical wire_id. Returns None if disabled or on fail-open
    error (we never let wire capture break the agent).
    """
    if is_disabled():
        return None
    try:
        wire_id = make_wire_id(request_body_bytes, response_body_bytes, started_at)
        wd = _wire_dir(wire_id, ecp_dir)
        wd.mkdir(parents=True, exist_ok=True)
        _safe_chmod(wd, SAFE_DIR_PERMS)

        # Parse request body if it looks like JSON to extract structural fields
        req_parsed: Optional[Dict[str, Any]] = None
        if request_body_bytes:
            try:
                parsed = json.loads(request_body_bytes)
                if isinstance(parsed, dict):
                    req_parsed = parsed
            except Exception:
                req_parsed = None

        request_model = (req_parsed or {}).get("model") if req_parsed else None
        system_prompt = (req_parsed or {}).get("system") if req_parsed else None
        tool_definitions = (req_parsed or {}).get("tools") if req_parsed else None
        messages = (req_parsed or {}).get("messages") if req_parsed else None
        is_streaming_request = bool((req_parsed or {}).get("stream")) if req_parsed else False

        ct = (response_content_type or "").lower()
        is_sse = "text/event-stream" in ct

        # Write the raw bytes to disk
        request_body_path = None
        if request_body_bytes:
            request_body_path = wd / "request.json"
            _atomic_write_bytes(request_body_path, request_body_bytes)

        response_body_path = None
        if response_body_bytes:
            response_body_path = wd / ("response.sse" if is_sse else "response.json")
            _atomic_write_bytes(response_body_path, response_body_bytes)

        # Hashes
        request_body_sha = _sha256_hex(request_body_bytes)
        response_body_sha = _sha256_hex(response_body_bytes)
        system_sha = _stable_sha_of_json(system_prompt)
        tools_sha = _stable_sha_of_json(tool_definitions)

        # Anthropic puts request-id in response headers (different cases possible)
        rid = None
        if response_headers:
            for k, v in response_headers.items():
                if (k or "").lower() == "request-id":
                    rid = v
                    break

        meta: Dict[str, Any] = {
            "wire_version": WIRE_VERSION,
            "schema": WIRE_SCHEMA,
            "wire_id": wire_id,
            "provider": provider,
            "request": {
                "url": request_url,
                "method": request_method,
                "headers": redact_headers(request_headers),
                "body_path": "request.json" if request_body_path else None,
                "body_sha256": request_body_sha,
                "body_bytes": len(request_body_bytes) if request_body_bytes else 0,
                "model": request_model,
                "system_prompt_sha256": system_sha,
                "tool_definitions_sha256": tools_sha,
                "tool_count": len(tool_definitions) if isinstance(tool_definitions, list) else 0,
                "message_count": len(messages) if isinstance(messages, list) else 0,
                "is_streaming": is_streaming_request,
            },
            "response": {
                "status": response_status,
                "headers": redact_headers(response_headers),
                "request_id": rid,
                "body_path": (response_body_path.name if response_body_path else None),
                "body_sha256": response_body_sha,
                "body_bytes": len(response_body_bytes) if response_body_bytes else 0,
                "content_type": response_content_type,
                "is_sse": is_sse,
            },
            "timing": {
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": int(round((finished_at - started_at) * 1000))
                               if (started_at and finished_at and finished_at >= started_at) else 0,
            },
            "error": error,
        }

        meta_path = wd / "meta.json"
        _atomic_write_text(meta_path, json.dumps(meta, indent=2, ensure_ascii=False))

        # Compact summary for embedding into record.meta — keeps records small
        # while still pointing at the on-disk wire vault.
        return {
            "wire_id": wire_id,
            "wire_version": WIRE_VERSION,
            "request_id": rid,
            "request_body_sha256": request_body_sha,
            "response_body_sha256": response_body_sha,
            "system_prompt_sha256": system_sha,
            "tool_definitions_sha256": tools_sha,
            "tool_count": meta["request"]["tool_count"],
            "message_count": meta["request"]["message_count"],
            "is_sse": is_sse,
            "response_bytes": meta["response"]["body_bytes"],
            "model": request_model,
            "status": response_status,
            "vault_path": f"vault/wire/{wire_id}",
        }
    except Exception as exc:
        # Fail-open: never block the agent on a wire-write failure.
        try:
            import structlog
            structlog.get_logger().warning(
                "wire_save_failed", error=str(exc), provider=provider
            )
        except Exception:
            try:
                print(f"  [atlast.wire] save failed: {exc}", flush=True)
            except Exception:
                pass
        return None


def list_wire_ids(ecp_dir: Optional[Path] = None) -> List[str]:
    """Return all wire_ids currently on disk, newest mtime first."""
    root = _wire_root(ecp_dir)
    if not root.exists():
        return []
    entries = []
    for p in root.iterdir():
        if p.is_dir() and p.name.startswith("wire_"):
            try:
                entries.append((p.stat().st_mtime, p.name))
            except Exception:
                continue
    entries.sort(reverse=True)
    return [name for _, name in entries]


def load_wire(wire_id: str, ecp_dir: Optional[Path] = None,
              include_body: bool = True) -> Optional[Dict[str, Any]]:
    """Read meta.json and optionally inline body bytes as text. Returns None
    if the wire entry is missing or malformed."""
    wd = _wire_dir(wire_id, ecp_dir)
    meta_path = wd / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if include_body:
        for section, default_name in (("request", "request.json"),):
            p = wd / default_name
            if p.exists():
                try:
                    meta[section]["body_text"] = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        is_sse = bool(meta.get("response", {}).get("is_sse"))
        rp = wd / ("response.sse" if is_sse else "response.json")
        if rp.exists():
            try:
                meta["response"]["body_text"] = rp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

    return meta


def verify_wire_integrity(wire_id: str, ecp_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Recompute disk hashes and compare against meta.json."""
    wd = _wire_dir(wire_id, ecp_dir)
    meta_path = wd / "meta.json"
    if not meta_path.exists():
        return {"ok": False, "wire_id": wire_id, "reason": "no_wire_evidence"}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "wire_id": wire_id, "reason": f"meta_json_unreadable: {e}"}

    issues: List[str] = []

    def _check(filename: str, claimed_sha: Optional[str]) -> None:
        p = wd / filename
        if not p.exists():
            if claimed_sha:
                issues.append(f"{filename}: missing on disk but meta has sha {claimed_sha}")
            return
        try:
            actual = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
        except Exception as exc:
            issues.append(f"{filename}: read failed: {exc}")
            return
        if claimed_sha and actual != claimed_sha:
            issues.append(f"{filename}: sha mismatch (disk={actual}, meta={claimed_sha})")

    _check("request.json", (meta.get("request") or {}).get("body_sha256"))
    is_sse = bool((meta.get("response") or {}).get("is_sse"))
    _check("response.sse" if is_sse else "response.json",
           (meta.get("response") or {}).get("body_sha256"))

    return {
        "ok": not issues,
        "wire_id": wire_id,
        "wire_version": meta.get("wire_version"),
        "issues": issues,
    }
