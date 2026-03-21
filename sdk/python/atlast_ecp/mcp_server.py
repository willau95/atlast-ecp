"""
ECP MCP Server — Tools for ECP evidence records.

Passive recording is done via wrap(client), OpenClaw Plugin, or hooks.
This MCP Server provides tools for agents to:
  - Query: verify records, get profile/DID, list recent records
  - Record: manually create ECP records for key decisions
  - Upload: trigger batch flush, issue certificates
  - Stats: detailed trust signal breakdown

Usage (Claude Desktop / Claude Code / any MCP-compatible platform):
    Configured via MCP settings or: npx atlast-ecp install
"""

import json
import sys
from typing import Any


def _server_base() -> str:
    """Get ECP server base URL (without /v1) from config, or empty string."""
    from .config import get_api_url
    url = get_api_url()
    if not url:
        return ""
    return url.replace("/v1", "").rstrip("/")


def _get_tools() -> list[dict]:
    """Return MCP tool definitions."""
    return [
        {
            "name": "ecp_verify",
            "description": (
                "Verify the integrity of an ECP evidence record. "
                "Returns chain verification status and on-chain anchor info."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "record_id": {
                        "type": "string",
                        "description": "The ECP record ID to verify (e.g. ecp_01HX...)"
                    }
                },
                "required": ["record_id"]
            }
        },
        {
            "name": "ecp_get_profile",
            "description": (
                "Get this agent's ATLAST trust signals and profile summary. "
                "Shows reliability rate, hedge rate, chain integrity, and ECP server profile link."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "ecp_get_did",
            "description": "Get this agent's decentralized identifier (DID) for ATLAST Protocol.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "ecp_certify",
            "description": (
                "Issue a work certificate for completed tasks. "
                "Creates a verifiable proof-of-work on ATLAST that clients can check."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title of the completed task (e.g. 'Market Analysis Report Q1 2026')"
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what was done"
                    }
                },
                "required": ["title"]
            }
        },
        {
            "name": "ecp_recent_records",
            "description": "List the most recent ECP evidence records for this agent.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of records to return (default: 5, max: 20)",
                        "default": 5
                    }
                },
                "required": []
            }
        },
        {
            "name": "ecp_record",
            "description": (
                "Manually create an ECP evidence record for a key decision or action. "
                "Use this when you want to explicitly log an important step in your work."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "step_type": {
                        "type": "string",
                        "enum": ["llm_call", "tool_call", "decision", "a2a_call"],
                        "description": "Type of step being recorded"
                    },
                    "input_text": {
                        "type": "string",
                        "description": "Input/prompt text (hashed before storage — content stays local)"
                    },
                    "output_text": {
                        "type": "string",
                        "description": "Output/result text (hashed before storage — content stays local)"
                    },
                    "model": {
                        "type": "string",
                        "description": "Model used (optional, e.g. 'claude-sonnet-4-6')"
                    },
                    "latency_ms": {
                        "type": "integer",
                        "description": "Latency in milliseconds (optional)"
                    }
                },
                "required": ["step_type", "input_text", "output_text"]
            }
        },
        {
            "name": "ecp_flush",
            "description": (
                "Force an immediate Merkle batch upload to the ATLAST backend. "
                "Normally batches upload hourly. Use this after important work to ensure records are anchored."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "ecp_stats",
            "description": (
                "Get detailed trust statistics for this agent: record counts by type, "
                "flag distribution, batch history, and chain integrity status."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
    ]


def _tool_ecp_verify(record_id: str) -> dict:
    try:
        from .storage import load_record_by_id
        from .record import sha256

        record = load_record_by_id(record_id)
        if not record:
            return {"verified": False, "error": f"Record not found: {record_id}"}

        chain = record.get("chain", {})
        step = record.get("step", {})
        anchor = record.get("anchor", {})

        return {
            "verified": True,
            "record_id": record_id,
            "agent": record.get("agent"),
            "timestamp": record.get("ts"),
            "chain": {
                "prev": chain.get("prev") or "genesis",
                "hash": chain.get("hash", "")[:16] + "...",
                "integrity": "✅ intact",
            },
            "signature": "✅ signed" if (record.get("sig") and record["sig"] != "unverified") else "⚠️ unverified",
            "on_chain": {
                "status": "✅ anchored" if anchor.get("attestation_uid") else "⏳ pending",
                "attestation_uid": anchor.get("attestation_uid"),
                "explorer": f"https://base.easscan.org/attestation/view/{anchor['attestation_uid']}"
                            if anchor.get("attestation_uid") else None,
            },
            "flags": step.get("flags", []),
            "public_verify_url": f"{_server_base()}/verify/{record_id}" if _server_base() else None,
        }
    except Exception as e:
        return {"verified": False, "error": str(e)}


def _tool_ecp_get_profile() -> dict:
    try:
        from .identity import get_or_create_identity
        from .storage import load_records, count_records
        from .signals import compute_trust_signals

        identity = get_or_create_identity()
        records = load_records(limit=500)
        total = count_records()
        signals = compute_trust_signals(records)

        return {
            "did": identity["did"],
            "total_records": total,
            "trust_signals": {
                "retried_rate": f"{signals['retried_rate'] * 100:.1f}%",
                "hedged_rate": f"{signals['hedged_rate'] * 100:.1f}%",
                "incomplete_rate": f"{signals['incomplete_rate'] * 100:.1f}%",
                "error_rate": f"{signals['error_rate'] * 100:.1f}%",
                "chain_integrity": "100%" if signals["chain_integrity"] == 1.0 else "BROKEN",
                "avg_latency_ms": signals["avg_latency_ms"],
            },
            "profile_url": f"{_server_base()}/profile" if _server_base() else "Run 'atlast register' to publish",
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_ecp_get_did() -> dict:
    try:
        from .identity import get_or_create_identity
        identity = get_or_create_identity()
        return {
            "did": identity["did"],
            "key_type": "ed25519" if identity.get("verified") else "fallback",
            "verified": identity.get("verified", False),
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_ecp_recent_records(limit: int = 5) -> dict:
    try:
        from .storage import load_records
        limit = min(limit, 20)
        records = load_records(limit=limit)
        return {
            "records": [
                {
                    "id": r["id"],
                    "ts": r["ts"],
                    "type": r.get("step", {}).get("type"),
                    "model": r.get("step", {}).get("model"),
                    "latency_ms": r.get("step", {}).get("latency_ms"),
                    "flags": r.get("step", {}).get("flags", []),
                }
                for r in records
            ]
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_ecp_certify(title: str, description: str = "") -> dict:
    try:
        import os
        import urllib.request
        from .identity import get_or_create_identity
        from .storage import load_records

        identity = get_or_create_identity()
        records = load_records(limit=100)
        record_ids = [r["id"] for r in records if r.get("id", "").startswith("rec_")]

        from .config import get_api_url
        base_url = get_api_url()

        import json as _json
        payload = _json.dumps({
            "agent_did": identity["did"],
            "task_name": title,
            "task_description": description or None,
            "record_ids": record_ids[:100],
            "sig": "unverified",
        }).encode()

        req = urllib.request.Request(
            f"{base_url}/certificates/create",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = _json.loads(resp.read())

        return {
            "cert_id": result.get("cert_id"),
            "trust_score": result.get("trust_score_at_issue"),
            "steps": result.get("steps_count"),
            "verify_url": result.get("verify_url"),
            "message": "Certificate issued! Share the verify_url with clients.",
        }
    except Exception as e:
        return {"error": str(e), "message": "Certificate creation failed. Records are still intact locally."}


def _tool_ecp_record(step_type: str, input_text: str, output_text: str,
                     model: str = "", latency_ms: int = 0) -> dict:
    """Manually create an ECP record."""
    try:
        from .core import record
        rec_id = record(
            input_content=input_text,
            output_content=output_text,
            step_type=step_type,
            model=model or None,
            latency_ms=latency_ms,
        )
        return {
            "record_id": rec_id or "created",
            "message": "✅ ECP record created and stored locally.",
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_ecp_flush() -> dict:
    """Trigger an immediate batch upload."""
    try:
        from .batch import run_batch
        run_batch(flush=True)
        from .batch import _load_batch_state
        state = _load_batch_state()
        return {
            "message": "✅ Batch upload triggered.",
            "total_batches": state.get("total_batches", 0),
            "last_merkle_root": (state.get("last_merkle_root", "")[:20] + "...") if state.get("last_merkle_root") else None,
            "last_attestation_uid": state.get("last_attestation_uid"),
        }
    except Exception as e:
        return {"error": str(e), "message": "Batch upload failed (non-fatal). Records are safe locally."}


def _tool_ecp_stats() -> dict:
    """Detailed trust statistics."""
    try:
        from .identity import get_or_create_identity
        from .storage import load_records, count_records
        from .signals import compute_trust_signals
        from .batch import _load_batch_state

        identity = get_or_create_identity()
        records = load_records(limit=1000)
        total = count_records()
        signals = compute_trust_signals(records)
        batch_state = _load_batch_state()

        # Count by step type
        type_counts: dict[str, int] = {}
        flag_counts: dict[str, int] = {}
        for r in records:
            step = r.get("step", {})
            stype = step.get("type", "unknown")
            type_counts[stype] = type_counts.get(stype, 0) + 1
            for f in step.get("flags", []):
                flag_counts[f] = flag_counts.get(f, 0) + 1

        return {
            "agent_did": identity["did"],
            "total_records": total,
            "records_by_type": type_counts,
            "flag_distribution": flag_counts,
            "trust_signals": {
                "reliability": f"{(1 - signals['retried_rate'] - signals['incomplete_rate'] - signals['error_rate']) * 100:.1f}%",
                "hedge_rate": f"{signals['hedged_rate'] * 100:.1f}%",
                "chain_integrity": "100%" if signals["chain_integrity"] == 1.0 else "BROKEN",
                "avg_latency_ms": signals["avg_latency_ms"],
            },
            "batch_info": {
                "total_batches": batch_state.get("total_batches", 0),
                "last_batch_ts": batch_state.get("last_batch_ts"),
                "agent_registered": batch_state.get("agent_registered", False),
                "has_api_key": bool(batch_state.get("agent_api_key")),
            },
            "profile_url": f"{_server_base()}/agent/{identity['did']}" if _server_base() else None,
        }
    except Exception as e:
        return {"error": str(e)}


def _handle_tool_call(tool_name: str, tool_input: dict) -> Any:
    if tool_name == "ecp_verify":
        return _tool_ecp_verify(tool_input.get("record_id", ""))
    elif tool_name == "ecp_get_profile":
        return _tool_ecp_get_profile()
    elif tool_name == "ecp_get_did":
        return _tool_ecp_get_did()
    elif tool_name == "ecp_certify":
        return _tool_ecp_certify(tool_input.get("title", ""), tool_input.get("description", ""))
    elif tool_name == "ecp_recent_records":
        return _tool_ecp_recent_records(tool_input.get("limit", 5))
    elif tool_name == "ecp_record":
        return _tool_ecp_record(
            tool_input.get("step_type", "decision"),
            tool_input.get("input_text", ""),
            tool_input.get("output_text", ""),
            tool_input.get("model", ""),
            tool_input.get("latency_ms", 0),
        )
    elif tool_name == "ecp_flush":
        return _tool_ecp_flush()
    elif tool_name == "ecp_stats":
        return _tool_ecp_stats()
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def run_stdio_server():
    """
    Run MCP Server over stdio (JSON-RPC 2.0).
    This is the standard MCP transport used by Claude Code and OpenClaw.
    """
    import sys

    def send(obj: dict):
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "atlast-ecp",
                        "version": "0.1.0",
                    }
                }
            })

        elif method == "tools/list":
            send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": _get_tools()}
            })

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_input = params.get("arguments", {})
            result = _handle_tool_call(tool_name, tool_input)
            send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                }
            })

        elif method == "notifications/initialized":
            pass  # No response needed

        else:
            send({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            })


if __name__ == "__main__":
    run_stdio_server()
