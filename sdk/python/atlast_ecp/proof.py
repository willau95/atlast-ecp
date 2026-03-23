"""
ECP Proof Package — shareable, self-contained, independently verifiable.

This is the bridge between "evidence on your machine" and "proof anyone can check".

A Proof Package contains:
  1. ECP records (hashes + chain + signatures)
  2. Content (optional — user decides what to include)
  3. Agent's public key (for signature verification)
  4. Verification instructions (so verifier needs ZERO setup)

The user CHOOSES what content to include (selective disclosure).
Hashes are always present — verifier can confirm content matches hash,
or note "content redacted" for records where content is withheld.

Usage:
    # Generate proof
    atlast proof --session sprint-42 --include-content -o proof.json
    
    # Verify (recipient — no atlast install needed, just python3)
    python3 -c "import json,hashlib; ..."  # inline verification
    
    # Or with atlast installed:
    atlast verify --proof proof.json

    # Or upload for web verification:
    atlast proof --session sprint-42 --upload
    → https://docs.weba0.com/verify/p/abc123

Privacy Model:
    - User ALWAYS controls what content is shared
    - Hashes are always included (they reveal nothing about content)
    - Content inclusion is opt-in, per-record granularity possible
    - "Redacted" records still have hash — verifier knows they exist
"""

import json
import hashlib
import time
from typing import Optional
from pathlib import Path


def generate_proof(
    record_ids: Optional[list[str]] = None,
    session_id: Optional[str] = None,
    include_content: bool = False,
    include_records: Optional[list[str]] = None,
    redact_records: Optional[list[str]] = None,
    limit: int = 100,
) -> dict:
    """
    Generate a self-contained Proof Package.

    Args:
        record_ids: Specific record IDs to include (None = all)
        session_id: Filter by session (None = all sessions)
        include_content: Include vault content for all records
        include_records: Only include content for these record IDs
        redact_records: Explicitly redact content for these record IDs
        limit: Max records to include

    Returns:
        Proof Package dict — JSON-serializable, self-contained.
    """
    from .storage import load_records, load_vault
    from .identity import get_or_create_identity
    from .record import compute_chain_hash, hash_content

    identity = get_or_create_identity()
    all_records = load_records(limit=limit)

    # Filter
    if record_ids:
        all_records = [r for r in all_records if r["id"] in record_ids]
    if session_id:
        filtered = []
        for r in all_records:
            sid = r.get("step", {}).get("session_id") or r.get("meta", {}).get("session_id")
            if sid == session_id:
                filtered.append(r)
        all_records = filtered

    if not all_records:
        return {"error": "No records found matching criteria"}

    # Build proof entries
    entries = []
    for r in all_records:
        entry = {
            "record": r,
            "chain_hash_verified": False,
            "content": None,
            "content_status": "redacted",  # redacted | included | unavailable
        }

        # Verify chain hash
        if "chain" in r and r["chain"].get("hash"):
            expected = compute_chain_hash(r)
            entry["chain_hash_verified"] = (expected == r["chain"]["hash"])

        # Include content if requested
        rid = r["id"]
        should_include = include_content
        if include_records and rid in include_records:
            should_include = True
        if redact_records and rid in redact_records:
            should_include = False

        if should_include:
            vault = load_vault(rid)
            if vault:
                # Verify content matches hashes
                in_hash_record = r.get("step", {}).get("in_hash") or r.get("in_hash", "")
                out_hash_record = r.get("step", {}).get("out_hash") or r.get("out_hash", "")

                in_verified = hash_content(vault["input"]) == in_hash_record
                out_verified = hash_content(vault["output"]) == out_hash_record

                entry["content"] = {
                    "input": vault["input"],
                    "output": vault["output"],
                    "input_hash_verified": in_verified,
                    "output_hash_verified": out_verified,
                }
                entry["content_status"] = "included"
            else:
                entry["content_status"] = "unavailable"

        entries.append(entry)

    # Build proof package
    proof = {
        "ecp_proof": "1.0",
        "generated_at": int(time.time() * 1000),
        "generator": "atlast-ecp",
        "agent": {
            "did": identity["did"],
            "public_key": identity.get("pub_key") or identity.get("public_key", ""),
        },
        "summary": {
            "total_records": len(entries),
            "content_included": sum(1 for e in entries if e["content_status"] == "included"),
            "content_redacted": sum(1 for e in entries if e["content_status"] == "redacted"),
            "chain_verified": sum(1 for e in entries if e["chain_hash_verified"]),
            "session_id": session_id,
        },
        "entries": entries,
        "verification": {
            "how_to_verify": [
                "1. For each entry, recompute SHA-256 of content → must match in_hash/out_hash",
                "2. Chain: each record's chain.prev must point to previous record's ID",
                "3. Chain hash: zero chain.hash and sig → JSON canonical → SHA-256 must match",
                "4. Signature: Ed25519 verify(public_key, sig, chain.hash)",
                "5. On-chain: check Merkle root on Base EAS (if anchored)",
            ],
            "online_verify": "https://docs.weba0.com/verify/",
            "hash_algorithm": "SHA-256",
            "signature_algorithm": "Ed25519",
            "canonical_json": "json.dumps(sort_keys=True, ensure_ascii=False, separators=(',',':'))",
        },
    }

    return proof


def verify_proof(proof: dict) -> dict:
    """
    Independently verify a Proof Package. No server needed.

    This can be run by ANYONE — the verifier doesn't need to trust the prover.

    Returns:
        {
            "valid": bool,
            "total_records": int,
            "chain_verified": int,
            "content_verified": int,
            "content_redacted": int,
            "signature_verified": int,
            "issues": [str],
        }
    """
    issues = []
    entries = proof.get("entries", [])
    pub_key = proof.get("agent", {}).get("public_key", "")

    chain_ok = 0
    content_ok = 0
    content_redacted = 0
    sig_ok = 0

    for i, entry in enumerate(entries):
        record = entry.get("record", {})
        rid = record.get("id", f"entry_{i}")

        # 1. Verify chain hash
        if "chain" in record and record["chain"].get("hash"):
            # Recompute chain hash
            copy = json.loads(json.dumps(record))
            copy["chain"]["hash"] = ""
            if "sig" in copy:
                copy["sig"] = ""
            canonical = json.dumps(copy, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            expected = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if expected == record["chain"]["hash"]:
                chain_ok += 1
            else:
                issues.append(f"{rid}: chain hash mismatch")

        # 2. Verify content hashes (if content included)
        content = entry.get("content")
        if content and entry.get("content_status") == "included":
            in_text = content.get("input", "")
            out_text = content.get("output", "")

            in_hash = record.get("step", {}).get("in_hash") or record.get("in_hash", "")
            out_hash = record.get("step", {}).get("out_hash") or record.get("out_hash", "")

            computed_in = "sha256:" + hashlib.sha256(in_text.encode("utf-8")).hexdigest()
            computed_out = "sha256:" + hashlib.sha256(out_text.encode("utf-8")).hexdigest()

            if computed_in == in_hash and computed_out == out_hash:
                content_ok += 1
            else:
                issues.append(f"{rid}: content hash mismatch")
        elif entry.get("content_status") == "redacted":
            content_redacted += 1

        # 3. Verify signature (if public key available)
        sig = record.get("sig", "")
        chain_hash = record.get("chain", {}).get("hash", "")
        if sig and sig.startswith("ed25519:") and pub_key and chain_hash:
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                sig_bytes = bytes.fromhex(sig[len("ed25519:"):])
                pub_bytes = bytes.fromhex(pub_key)
                key = Ed25519PublicKey.from_public_bytes(pub_bytes)
                key.verify(sig_bytes, chain_hash.encode())
                sig_ok += 1
            except ImportError:
                pass  # No cryptography package — skip sig verification
            except Exception:
                issues.append(f"{rid}: signature verification failed")

    total = len(entries)
    valid = len(issues) == 0 and chain_ok > 0

    return {
        "valid": valid,
        "total_records": total,
        "chain_verified": chain_ok,
        "content_verified": content_ok,
        "content_redacted": content_redacted,
        "signature_verified": sig_ok,
        "issues": issues,
    }


def format_proof_report(proof: dict, verification: Optional[dict] = None) -> str:
    """Format proof for human-readable display."""
    lines = []
    lines.append("")
    lines.append("🔗 ATLAST ECP — Proof Package")
    lines.append("=" * 60)

    summary = proof.get("summary", {})
    agent = proof.get("agent", {})

    lines.append(f"  Agent DID:  {agent.get('did', '?')}")
    lines.append(f"  Records:    {summary.get('total_records', 0)}")
    lines.append(f"  Content:    {summary.get('content_included', 0)} included, "
                 f"{summary.get('content_redacted', 0)} redacted")
    lines.append(f"  Session:    {summary.get('session_id') or 'all'}")

    if verification:
        lines.append("")
        v = verification
        status = "✅ VALID" if v["valid"] else "❌ ISSUES FOUND"
        lines.append(f"  Verification: {status}")
        lines.append(f"    Chain hashes:  {v['chain_verified']}/{v['total_records']} verified")
        lines.append(f"    Content:       {v['content_verified']} verified, "
                     f"{v['content_redacted']} redacted")
        lines.append(f"    Signatures:    {v['signature_verified']} verified")
        if v["issues"]:
            lines.append(f"    Issues:")
            for issue in v["issues"]:
                lines.append(f"      ❌ {issue}")

    # Show entries
    for i, entry in enumerate(proof.get("entries", [])):
        record = entry.get("record", {})
        step = record.get("step", {})
        meta = record.get("meta", {})

        rid = record.get("id", "?")
        action = step.get("type") or record.get("action", "?")
        model = step.get("model") or meta.get("model", "—")
        tokens_out = step.get("tokens_out") or meta.get("tokens_out", "—")
        latency = step.get("latency_ms") or meta.get("latency_ms", 0)
        session = step.get("session_id") or meta.get("session_id", "—")
        flags = step.get("flags") or meta.get("flags", [])

        lines.append("")
        lines.append(f"  ── Record {i+1}: {rid} ──")
        lines.append(f"  Action: {action} | Model: {model} | {latency}ms | {tokens_out} tokens out")
        if flags:
            lines.append(f"  Flags: {' '.join(f'⚡{f}' for f in flags)}")
        lines.append(f"  Chain: {'✅' if entry.get('chain_hash_verified') else '—'} | "
                     f"Content: {entry.get('content_status', '?')}")

        content = entry.get("content")
        if content:
            in_text = content.get("input", "")[:200]
            out_text = content.get("output", "")[:300]
            in_ok = "✅" if content.get("input_hash_verified") else "❌"
            out_ok = "✅" if content.get("output_hash_verified") else "❌"
            lines.append(f"  Input {in_ok}: {in_text}{'...' if len(content.get('input',''))>200 else ''}")
            lines.append(f"  Output {out_ok}: {out_text}{'...' if len(content.get('output',''))>300 else ''}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
