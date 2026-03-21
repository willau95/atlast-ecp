"""
ECP CLI — atlast command line interface

Commands:
    atlast init              Initialize ~/.ecp/ directory
    atlast init --identity   Initialize + generate Ed25519 DID
    atlast record            Record an ECP entry (stdin or flags)
    atlast log               View latest ECP records
    atlast verify <id>       Verify a record's chain integrity
    atlast stats             Show agent trust signals
    atlast did               Show this agent's DID
    atlast push              Upload records to ECP server (opt-in)
    atlast flush             Alias for push
    atlast proxy             Start local transparent proxy
    atlast run <cmd>         Run command with proxy auto-injected
    atlast register          Register agent with ATLAST Backend
    atlast certify <title>   Issue a work certificate
    atlast export            Export records as JSON
    atlast view              Alias for log
"""

import json
import sys
from datetime import datetime, timezone
from atlast_ecp import __version__


def _print_record(record: dict, show_chain: bool = False):
    """Print a record, handling both v0.1 (nested step) and v1.0 (flat) formats."""
    # v1.0 flat format
    if record.get("ecp") == "1.0":
        meta = record.get("meta", {})
        flags = meta.get("flags", [])
        ts = record.get("ts", 0)
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        flag_str = " ".join(f"[{f.upper()}]" for f in flags) if flags else ""
        latency = meta.get("latency_ms")
        latency_str = f"  {latency}ms" if latency else ""

        print(f"  {record['id']}")
        print(f"  {dt}{latency_str}  {flag_str}")
        print(f"  Action: {record.get('action', '?')} | Model: {meta.get('model') or '—'}")
        if meta.get("tokens_in"):
            print(f"  Tokens: {meta['tokens_in']} in / {meta.get('tokens_out', '?')} out")
        print()
        return

    # v0.1 nested format (backward compat)
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
    """atlast verify <record_id> OR atlast verify --a2a file1.jsonl file2.jsonl ..."""
    from .config import get_api_url
    if not args:
        print("Usage: atlast verify <record_id>")
        print("       atlast verify --a2a file1.jsonl file2.jsonl [--json]")
        sys.exit(1)

    if args[0] == "--a2a":
        return _cmd_verify_a2a(args[1:])
    

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

    server_url = get_api_url()
    if server_url:
        print(f"\n  View on server: {server_url.replace('/v1', '')}/verify/{record_id}\n")
    else:
        print(f"\n  Record ID: {record_id}  (configure ATLAST_API_URL to view online)\n")


def _cmd_verify_a2a(args: list[str]):
    """atlast verify --a2a file1.jsonl file2.jsonl [--json]"""
    import json as json_mod
    from .a2a import build_a2a_chain, verify_a2a_chain, format_a2a_report

    output_json = "--json" in args
    files = [a for a in args if a != "--json"]

    if not files:
        print("Usage: atlast verify --a2a file1.jsonl file2.jsonl [--json]")
        sys.exit(1)

    all_records = []
    for f in files:
        if not os.path.exists(f):
            print(f"❌ File not found: {f}")
            sys.exit(1)
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    all_records.append(json_mod.loads(line))

    if not all_records:
        print("❌ No records found in input files")
        sys.exit(1)

    chain = build_a2a_chain(all_records)
    report = verify_a2a_chain(chain)

    if output_json:
        result = {
            "valid": report.valid,
            "agents": report.agents,
            "total_handoffs": report.total_handoffs,
            "valid_handoffs": report.valid_handoffs,
            "invalid_handoffs": report.invalid_handoffs,
            "causal_violations": report.causal_violations,
            "orphan_count": report.orphan_count,
            "blame_trace": report.blame_trace,
        }
        print(json_mod.dumps(result, indent=2))
    else:
        print(format_a2a_report(report))

    sys.exit(0 if report.valid else 1)


def cmd_stats(args: list[str]):
    from .config import get_api_url
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
    server_url = get_api_url()
    if server_url:
        print(f"  Full profile: {server_url.replace('/v1', '')}  (register to publish)")
    else:
        print(f"  Run 'atlast register' to publish your profile to an ECP server")
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
    """atlast flush [--endpoint URL] [--key ak_live_xxx] — force Merkle batch upload now"""
    import os
    from .config import get_api_url, get_api_key

    endpoint = None
    key = None
    for i, a in enumerate(args):
        if a == "--endpoint" and i + 1 < len(args):
            endpoint = args[i + 1]
        if a == "--key" and i + 1 < len(args):
            key = args[i + 1]

    # Priority: CLI arg > env var > config file
    if endpoint:
        os.environ["ATLAST_API_URL"] = endpoint

    # Resolve key: CLI > env > config > batch_state
    resolved_key = key or get_api_key()

    from .batch import trigger_batch_upload, _load_batch_state, _save_batch_state

    if resolved_key:
        state = _load_batch_state()
        state["agent_api_key"] = resolved_key
        _save_batch_state(state)

    target = endpoint or get_api_url()
    print(f"⏫ Triggering Merkle batch upload → {target}")
    trigger_batch_upload(flush=True)
    import time; time.sleep(2)
    print("✅ Done (check .ecp/batch_state.json for result)")


def cmd_register(args: list[str]):
    """atlast register — register agent DID with ATLAST Backend"""
    import urllib.request
    from .identity import get_or_create_identity
    from .config import get_api_url, save_config

    # Parse optional --name for display_name
    display_name = None
    for i, a in enumerate(args):
        if a == "--name" and i + 1 < len(args):
            display_name = args[i + 1]

    identity = get_or_create_identity()
    did = identity["did"]
    pub_key = identity.get("pub_key", "")

    print(f"\n🔗 Registering Agent...")

    body: dict = {
        "did": did,
        "public_key": pub_key,
        "ecp_version": "0.1",
    }
    if display_name:
        body["display_name"] = display_name

    payload = json.dumps(body).encode()

    base_url = get_api_url()
    backend_url = f"{base_url}/agents/register"

    try:
        req = urllib.request.Request(
            backend_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())

        agent_name = result.get("display_name") or result.get("handle") or did
        api_key = result.get("agent_api_key", "")
        claim_url = result.get("claim_url", "")

        print(f"  ✓ Agent registered: {agent_name}")
        print(f"  ✓ DID: {did}")
        if api_key:
            print(f"  ✓ API Key: {api_key}  ← (save this, shown once)")
        if claim_url:
            print(f"  ✓ Claim URL: {claim_url}")
        print()
        print(f"  Next: Send this claim URL to your owner to activate your profile.")

        # Save to local config
        config_data = {"agent_did": did, "endpoint": base_url}
        if api_key:
            config_data["agent_api_key"] = api_key
        save_config(config_data)

    except Exception as e:
        error_str = str(e)
        if "409" in error_str:
            print(f"  ✓ Agent already registered: {did}")
            server_url = get_api_url()
            if server_url:
                print(f"  🌐 Profile: {server_url.replace('/v1', '')}/agent/{did}")
        else:
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

    from .config import get_api_url, get_api_key

    base_url = get_api_url()

    payload = json.dumps({
        "agent_did": did,
        "task_name": title,
        "task_description": description,
        "record_ids": record_ids[:100],
        "sig": "unverified",
    }).encode()

    try:
        headers = {"Content-Type": "application/json"}
        api_key = get_api_key()
        if api_key:
            headers["X-Agent-Key"] = api_key

        req = urllib.request.Request(
            f"{base_url}/certificates/create",
            data=payload,
            headers=headers,
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
    """atlast init [--minimal] — initialize ~/.ecp/ directory + generate DID"""
    from .storage import init_storage
    init_storage()

    skip_identity = "--minimal" in args or "--no-identity" in args

    print(f"\n🔗 ATLAST ECP initialized")
    print(f"  Storage: ~/.ecp/records/ (local, private)")

    if not skip_identity:
        from .identity import get_or_create_identity
        identity = get_or_create_identity()
        print(f"  Agent DID: {identity['did']}")
        print(f"  Key type: {'ed25519' if identity.get('verified') else 'fallback'}")
        print(f"\n  Next: atlast register (optional — publish to an ECP server)")
    else:
        print(f"  Identity: skipped (run 'atlast init' to create DID)")
        print(f"\n  Next: echo '{{\"in\":\"prompt\",\"out\":\"response\"}}' | atlast record")
    print()


def cmd_record(args: list[str]):
    """atlast record — create an ECP record from stdin or flags"""
    from .record import create_minimal_record, create_record, hash_content
    from .storage import save_record
    import os

    agent = "default"
    action = "llm_call"
    in_content = None
    out_content = None
    full_mode = "--full" in args

    # Parse flags
    for i, a in enumerate(args):
        if a == "--agent" and i + 1 < len(args):
            agent = args[i + 1]
        if a == "--action" and i + 1 < len(args):
            action = args[i + 1]
        if a == "--in" and i + 1 < len(args):
            in_content = args[i + 1]
        if a == "--out" and i + 1 < len(args):
            out_content = args[i + 1]

    # If no --in/--out, read from stdin
    if in_content is None and out_content is None:
        if not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
            if raw:
                try:
                    data = json.loads(raw)
                    in_content = data.get("in", data.get("input", ""))
                    out_content = data.get("out", data.get("output", ""))
                    agent = data.get("agent", agent)
                    action = data.get("action", action)
                except json.JSONDecodeError:
                    print("Error: stdin must be valid JSON with 'in' and 'out' fields")
                    sys.exit(1)
        else:
            print("Usage: atlast record --in 'prompt' --out 'response'")
            print("   or: echo '{\"in\":\"...\",\"out\":\"...\"}' | atlast record")
            sys.exit(1)

    if in_content is None or out_content is None:
        print("Error: both 'in' and 'out' content required")
        sys.exit(1)

    if full_mode:
        # Full v0.1 record with chain + signature
        from .identity import get_or_create_identity
        identity = get_or_create_identity()
        rec_obj = create_record(
            agent_did=identity["did"],
            step_type=action,
            in_content=in_content,
            out_content=out_content,
            identity=identity,
        )
        from .record import record_to_dict
        rec = record_to_dict(rec_obj)
    else:
        # Minimal v1.0 record
        rec = create_minimal_record(agent, action, in_content, out_content)

    save_record(rec)
    print(f"✅ {rec['id']}")


def cmd_log(args: list[str]):
    """atlast log [--limit N] [--date YYYY-MM-DD] — view ECP records (alias: view)"""
    cmd_view(args)


def cmd_push(args: list[str]):
    """atlast push [--endpoint URL] [--key KEY] — upload records to ECP server"""
    cmd_flush(args)


def cmd_proxy(args: list[str]):
    """atlast proxy [--port PORT] — start local transparent proxy"""
    port = 8340
    agent = "proxy"
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        if a == "--agent" and i + 1 < len(args):
            agent = args[i + 1]

    try:
        from .proxy import run_proxy
        run_proxy(port=port, agent=agent)
    except ImportError:
        print("Proxy requires aiohttp. Install with: pip install atlast-ecp[proxy]")
        sys.exit(1)


def cmd_run(args: list[str]):
    """atlast run <command> — run command with proxy auto-injected"""
    if not args:
        print("Usage: atlast run python my_agent.py")
        sys.exit(1)

    try:
        from .proxy import run_with_proxy
        run_with_proxy(args)
    except ImportError:
        print("Proxy requires aiohttp. Install with: pip install atlast-ecp[proxy]")
        sys.exit(1)


def _cmd_insights(args: list[str]):
    """atlast insights [--json] [--top N] [--limit N] — analyze ECP records"""
    from .insights import cmd_insights
    cmd_insights(args)


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


def _cmd_config(args: list[str]):
    """atlast config get|set <key> [value] — manage ~/.atlast/config.json"""
    from .config import load_config, save_config

    if not args:
        print("Usage:")
        print("  atlast config get              Show all config")
        print("  atlast config set <key> <val>  Set a config value")
        print("  atlast config get <key>        Get a specific value")
        print("\nKeys: endpoint, api_key, agent_did, webhook_url, webhook_token")
        return

    sub = args[0]
    if sub == "get":
        cfg = load_config()
        if len(args) >= 2:
            key = args[1]
            val = cfg.get(key)
            if val is not None:
                # Mask sensitive values
                if "token" in key or "key" in key:
                    val = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
                print(f"{key} = {val}")
            else:
                print(f"{key}: not set")
        else:
            if not cfg:
                print("No config found. Run 'atlast init' or 'atlast config set <key> <val>'")
                return
            for k, v in cfg.items():
                display = v
                if ("token" in k or "key" in k) and isinstance(v, str) and len(v) > 12:
                    display = v[:8] + "..." + v[-4:]
                print(f"  {k} = {display}")
    elif sub == "set":
        if len(args) < 3:
            print("Usage: atlast config set <key> <value>")
            sys.exit(1)
        key, value = args[1], args[2]
        save_config({key: value})
        print(f"✅ {key} saved to ~/.atlast/config.json")
    else:
        print(f"Unknown config subcommand: {sub}")
        sys.exit(1)


def _cmd_discover(args: list[str]):
    """atlast discover <url> — discover ECP server capabilities"""
    import urllib.request
    import urllib.error

    if not args:
        print("Usage: atlast discover <server-url>")
        print("Example: atlast discover http://localhost:8900")
        return

    base_url = args[0].rstrip("/")
    url = f"{base_url}/.well-known/ecp.json"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"❌ Server returned HTTP {e.code}: {url}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Could not reach server: {e}")
        sys.exit(1)

    print(f"\n🔍 ECP Server Discovery: {base_url}")
    print("=" * 50)
    print(f"  ECP Version:    {data.get('ecp_version', '?')}")
    print(f"  Server Version: {data.get('server_version', '?')}")
    print(f"  Server Name:    {data.get('server_name', '?')}")

    caps = data.get("capabilities", [])
    if caps:
        print(f"\n  Capabilities: {', '.join(caps)}")

    endpoints = data.get("endpoints", [])
    if endpoints:
        print(f"\n  Endpoints ({len(endpoints)}):")
        for ep in endpoints:
            print(f"    {ep.get('method', '?'):6s} {ep.get('path', '?')}")

    auth = data.get("auth_methods", [])
    if auth:
        print(f"\n  Auth: {', '.join(auth)}")

    chain = data.get("chain")
    if chain:
        print(f"\n  Chain: {chain}")

    print()


def main():
    args = sys.argv[1:]
    if not args:
        print(f"ATLAST ECP — Evidence Chain Protocol v{__version__}\n")
        print("  Getting started:")
        print("    atlast init              Initialize ~/.ecp/ (add --identity for DID)")
        print("    atlast record            Create ECP record (stdin or --in/--out)")
        print("    atlast log               View latest records")
        print()
        print("  Zero-code integration:")
        print("    atlast proxy             Start local transparent proxy")
        print("    atlast run <cmd>         Run command with proxy auto-injected")
        print()
        print("  Analysis:")
        print("    atlast insights          Analyze records (latency, errors, models)")
        print("    atlast insights --section performance|trends|tools")
        print("    atlast verify <id>       Verify record integrity")
        print("    atlast stats             Show trust signals")
        print("    atlast did               Show agent DID")
        print()
        print("  Publishing (opt-in):")
        print("    atlast register          Register agent with ATLAST Backend")
        print("    atlast push              Upload records to ECP server")
        print("    atlast certify <title>   Issue a work certificate")
        print("    atlast export            Export records as JSON")
        print()
        print("  Configuration:")
        print("    atlast config get        Show current config")
        print("    atlast config set <k> <v>  Set config value")
        print("    atlast discover <url>    Discover ECP server capabilities")
        print()
        print("  Docs: https://github.com/willau95/atlast-ecp")
        return

    cmd = args[0]
    rest = args[1:]

    commands = {
        "init": cmd_init,
        "record": cmd_record,
        "log": cmd_log,
        "view": cmd_view,      # backward compat alias
        "verify": cmd_verify,
        "stats": cmd_stats,
        "did": cmd_did,
        "push": cmd_push,
        "flush": cmd_flush,    # backward compat alias
        "proxy": cmd_proxy,
        "run": cmd_run,
        "register": cmd_register,
        "certify": cmd_certify,
        "export": cmd_export,
        "insights": _cmd_insights,
        "config": _cmd_config,
        "discover": _cmd_discover,
    }

    if cmd in ("--help", "-h", "help"):
        main.__wrapped__ = True  # prevent recursion
        # Re-run with no args to show help
        sys.argv = [sys.argv[0]]
        main()
        return

    if cmd in ("--version", "-V"):
        print(f"atlast-ecp {__version__}")
        return

    if cmd in commands:
        commands[cmd](rest)
    else:
        print(f"Unknown command: {cmd}")
        print("Run 'atlast' or 'atlast --help' for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
