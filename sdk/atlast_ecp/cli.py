"""
ECP CLI — atlast command line interface

Commands:
    atlast view              View latest ECP records
    atlast verify <id>       Verify a record's chain integrity
    atlast stats             Show agent trust signals
    atlast did               Show this agent's DID
    atlast flush             Force upload Merkle batch now
"""

import json
import sys
from datetime import datetime, timezone


def _print_record(record: dict, show_chain: bool = False):
    step = record.get("step", {})
    chain = record.get("chain", {})
    flags = step.get("flags", [])
    ts = record.get("ts", 0)
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    flag_str = " ".join(f"[{f.upper()}]" for f in flags) if flags else ""
    latency = step.get("latency_ms")
    latency_str = f"  {latency}ms" if latency else ""

    print(f"  {record['id']}")
    print(f"  {dt}{latency_str}  {flag_str}")
    print(f"  Type: {step.get('type', '?')} | Model: {step.get('model') or '—'}")
    if step.get("tokens_in"):
        print(f"  Tokens: {step['tokens_in']} in / {step.get('tokens_out', '?')} out")
    if show_chain:
        print(f"  Chain hash: {chain.get('hash', '?')[:32]}...")
        print(f"  Prev: {chain.get('prev') or 'genesis'}")
    print()


def cmd_view(args: list[str]):
    """atlast view [--limit N] [--date YYYY-MM-DD]"""
    from .storage import load_records
    limit = 10
    date = None
    for i, a in enumerate(args):
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        if a == "--date" and i + 1 < len(args):
            date = args[i + 1]

    records = load_records(limit=limit, date=date)
    if not records:
        print("No ECP records found. Start using your Agent to generate evidence.")
        return

    print(f"\n🔗 ECP Evidence Chain — Latest {len(records)} records\n")
    for r in records:
        _print_record(r)


def cmd_verify(args: list[str]):
    """atlast verify <record_id>"""
    if not args:
        print("Usage: atlast verify <record_id>")
        sys.exit(1)

    record_id = args[0]
    from .storage import load_record_by_id

    record = load_record_by_id(record_id)
    if not record:
        print(f"❌ Record not found: {record_id}")
        sys.exit(1)

    print(f"\n🔍 Verifying ECP Record: {record_id}\n")

    # 1. Chain hash integrity check (always verify, regardless of prev)
    chain = record.get("chain", {})
    prev_id = chain.get("prev")
    chain_ok = True

    from .record import compute_chain_hash
    expected_hash = compute_chain_hash(record)
    actual_hash = chain.get("hash", "")
    if expected_hash == actual_hash:
        print(f"  ✅ Chain hash verified")
    else:
        print(f"  ❌ Chain hash mismatch — record may have been tampered")
        chain_ok = False

    # 1b. Chain link check (prev record exists?)
    if prev_id and prev_id != "genesis":
        prev_record = load_record_by_id(prev_id)
        if not prev_record:
            print(f"  ⚠️  Previous record not found: {prev_id}")
        else:
            print(f"  ✅ Chain link: → {prev_id}")
    elif prev_id == "genesis":
        print(f"  ✅ Genesis record (first in chain)")

    # 2. Signature check
    if record.get("sig") and record["sig"] != "unverified":
        print(f"  ✅ Signature present: {record['sig'][:32]}...")
    else:
        print(f"  ⚠️  Signature: unverified (cryptography package not installed)")

    # 3. On-chain anchor
    anchor = record.get("anchor", {})
    if anchor.get("attestation_uid"):
        uid = anchor["attestation_uid"]
        print(f"  ✅ On-chain: EAS Base — {uid[:20]}...")
        print(f"     https://base.easscan.org/attestation/view/{uid}")
    else:
        print(f"  ⏳ On-chain: Pending next Merkle batch (runs hourly)")

    # 4. Summary
    print()
    if chain_ok:
        print(f"  🟢 VERIFIED — Record integrity confirmed")
    else:
        print(f"  🔴 INTEGRITY ISSUE — Chain may be broken")

    print(f"\n  View public proof: https://llachat.com/verify/{record_id}\n")


def cmd_stats(args: list[str]):
    """atlast stats"""
    from .storage import load_records, count_records
    from .signals import compute_trust_signals

    records = load_records(limit=1000)
    total = count_records()
    signals = compute_trust_signals(records)

    print(f"\n📊 ATLAST Trust Signals\n")

    from .identity import get_or_create_identity
    identity = get_or_create_identity()
    print(f"  Agent: {identity['did']}")
    print(f"  Total records: {total}")
    print()

    def _bar(rate, width=20):
        filled = int((1 - rate) * width)
        return "█" * filled + "░" * (width - filled)

    retry_r = signals["retried_rate"]
    hedge_r = signals["hedged_rate"]
    incomplete_r = signals["incomplete_rate"]
    error_r = signals["error_rate"]
    chain_i = signals["chain_integrity"]

    print(f"  Reliability     {_bar(retry_r + incomplete_r + error_r)}  "
          f"{int((1 - retry_r - incomplete_r - error_r) * 100)}%")
    print(f"  Hedge rate      {hedge_r * 100:.1f}%  (lower = more decisive)")
    print(f"  Chain integrity {'✅ 100%' if chain_i == 1.0 else '⚠️ BROKEN'}")
    print(f"  Avg latency     {signals['avg_latency_ms']}ms")
    print()
    print(f"  Full profile: https://llachat.com  (register to publish)")
    print()


def cmd_did(args: list[str]):
    """atlast did"""
    from .identity import get_or_create_identity
    identity = get_or_create_identity()
    print(f"\n  Agent DID: {identity['did']}")
    print(f"  Key type: {'ed25519 (verified)' if identity.get('verified') else 'fallback (unverified)'}")
    print(f"  Created: {identity.get('created_at', 'unknown')}")
    print()


def cmd_flush(args: list[str]):
    """atlast flush — force Merkle batch upload now"""
    from .batch import trigger_batch_upload
    print("⏫ Triggering Merkle batch upload...")
    trigger_batch_upload(flush=True)
    import time; time.sleep(2)
    print("✅ Done (check .ecp/batch_state.json for result)")


def cmd_register(args: list[str]):
    """atlast register — register agent DID with ATLAST Backend"""
    import urllib.request
    from .identity import get_or_create_identity

    identity = get_or_create_identity()
    did = identity["did"]
    pub_key = identity.get("pub_key", "")

    print(f"\n🔗 Registering Agent: {did}")

    payload = json.dumps({
        "did": did,
        "public_key": pub_key,
        "ecp_version": "0.1",
    }).encode()

    import os
    base_url = os.environ.get(
        "ATLAST_API_URL",
        "https://llachat-backend-production.up.railway.app/v1"
    )
    backend_url = f"{base_url}/agent/register"

    try:
        req = urllib.request.Request(
            backend_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        print(f"  ✅ Registered! Agent ID: {result.get('agent_id', did)}")
        print(f"  🌐 Profile: https://llachat.com/agent/{did}")
    except Exception as e:
        # Fail-Open: registration failure is non-fatal
        print(f"  ⚠️  Backend not available yet (non-fatal): {e}")
        print(f"  📁 Local recording continues. Register later with: atlast register")
    print()


def cmd_certify(args: list[str]):
    """atlast certify <title> [--desc description]"""
    import urllib.request
    from .identity import get_or_create_identity
    from .storage import load_records

    if not args:
        print("Usage: atlast certify <title> [--desc description]")
        return

    title = args[0]
    description = None
    for i, a in enumerate(args):
        if a == "--desc" and i + 1 < len(args):
            description = " ".join(args[i + 1:])
            break

    identity = get_or_create_identity()
    did = identity["did"]

    # Collect recent record IDs
    records = load_records(limit=100)
    record_ids = [r["id"] for r in records if r.get("id", "").startswith("rec_")]

    print(f"\n📜 Creating Work Certificate")
    print(f"  Agent: {did}")
    print(f"  Task: {title}")
    print(f"  Records: {len(record_ids)}")

    import os
    base_url = os.environ.get(
        "ATLAST_API_URL",
        "https://llachat-backend-production.up.railway.app/v1"
    )

    payload = json.dumps({
        "agent_did": did,
        "task_name": title,
        "task_description": description,
        "record_ids": record_ids[:100],
        "sig": "unverified",
    }).encode()

    try:
        req = urllib.request.Request(
            f"{base_url}/certificate/create",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        print(f"\n  ✅ Certificate issued!")
        print(f"  🆔 {result.get('cert_id')}")
        print(f"  📊 Trust Score: {result.get('trust_score_at_issue')}")
        print(f"  🔗 Verify: {result.get('verify_url')}")
    except Exception as e:
        print(f"\n  ⚠️  Certificate creation failed: {e}")
        print(f"  📁 Local records are intact. Try again later.")
    print()


def cmd_init(args: list[str]):
    """atlast init — initialize .ecp/ and generate DID"""
    from .identity import get_or_create_identity
    from .storage import init_storage
    init_storage()
    identity = get_or_create_identity()
    print(f"\n🔗 ATLAST ECP initialized")
    print(f"  Agent DID: {identity['did']}")
    print(f"  Storage: .ecp/ (local, private)")
    print(f"  Key type: {'ed25519' if identity.get('verified') else 'fallback'}")
    print(f"\n  Next: Register at https://llachat.com")
    print()


def cmd_export(args: list[str]):
    """atlast export [--format json] — export ECP records"""
    import json as _json
    from .storage import load_records
    limit = 100
    for i, a in enumerate(args):
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])

    records = load_records(limit=limit)
    if not records:
        print("No records to export.")
        return

    output = _json.dumps(records, indent=2, ensure_ascii=False)
    print(output)


def main():
    args = sys.argv[1:]
    if not args:
        print("ATLAST ECP CLI v0.1.0\n")
        print("  atlast init              Initialize .ecp/ and generate DID")
        print("  atlast register          Register agent with ATLAST Backend")
        print("  atlast view              View latest ECP records")
        print("  atlast verify <id>       Verify a record's integrity")
        print("  atlast stats             Show agent trust signals")
        print("  atlast did               Show this agent's DID")
        print("  atlast flush             Force Merkle batch upload")
        print("  atlast certify <title>   Issue a work certificate")
        print("  atlast export            Export records as JSON")
        print()
        print("  Docs: https://github.com/willau95/atlast-ecp")
        return

    cmd = args[0]
    rest = args[1:]

    commands = {
        "init": cmd_init,
        "register": cmd_register,
        "view": cmd_view,
        "verify": cmd_verify,
        "stats": cmd_stats,
        "did": cmd_did,
        "flush": cmd_flush,
        "certify": cmd_certify,
        "export": cmd_export,
    }

    if cmd in commands:
        commands[cmd](rest)
    else:
        print(f"Unknown command: {cmd}")
        print("Run 'atlast' for help.")
        sys.exit(1)


if __name__ == "__main__":
    main()
