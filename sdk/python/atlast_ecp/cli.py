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
import os
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

    if args[0] == "--proof":
        return _cmd_verify_proof(args[1:])


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
        print("  ✅ Chain hash verified")
    else:
        print("  ❌ Chain hash mismatch — record may have been tampered")
        chain_ok = False

    # 1b. Chain link check (prev record exists?)
    if prev_id and prev_id != "genesis":
        prev_record = load_record_by_id(prev_id)
        if not prev_record:
            print(f"  ⚠️  Previous record not found: {prev_id}")
        else:
            print(f"  ✅ Chain link: → {prev_id}")
    elif prev_id == "genesis":
        print("  ✅ Genesis record (first in chain)")

    # 2. Signature check
    if record.get("sig") and record["sig"] != "unverified":
        print(f"  ✅ Signature present: {record['sig'][:32]}...")
    else:
        print("  ⚠️  Signature: unverified (cryptography package not installed)")

    # 3. On-chain anchor
    anchor = record.get("anchor", {})
    if anchor.get("attestation_uid"):
        uid = anchor["attestation_uid"]
        print(f"  ✅ On-chain: EAS Base — {uid[:20]}...")
        print(f"     https://base.easscan.org/attestation/view/{uid}")
    else:
        print("  ⏳ On-chain: Pending next Merkle batch (runs hourly)")

    # 4. Summary
    print()
    if chain_ok:
        print("  🟢 VERIFIED — Record integrity confirmed")
    else:
        print("  🔴 INTEGRITY ISSUE — Chain may be broken")

    server_url = get_api_url()
    if server_url:
        print(f"\n  View on server: {server_url.replace('/v1', '')}/verify/{record_id}\n")
    else:
        print(f"\n  Record ID: {record_id}  (configure ATLAST_API_URL to view online)\n")


def _cmd_verify_proof(args: list[str]):
    """atlast verify --proof file.json — independently verify a proof package"""
    if not args:
        print("Usage: atlast verify --proof <file.json>")
        sys.exit(1)

    proof_file = args[0]
    if not os.path.exists(proof_file):
        print(f"❌ File not found: {proof_file}")
        sys.exit(1)

    with open(proof_file) as f:
        proof = json.load(f)

    from .proof import verify_proof, format_proof_report

    verification = verify_proof(proof)
    print(format_proof_report(proof, verification))

    sys.exit(0 if verification["valid"] else 1)


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
    """atlast stats"""
    from .config import get_api_url
    from .storage import load_records, count_records
    from .signals import compute_trust_signals

    records = load_records(limit=1000)
    total = count_records()
    signals = compute_trust_signals(records)

    print("\n📊 ATLAST Trust Signals\n")

    from .identity import get_or_create_identity
    identity = get_or_create_identity()
    did_short = identity['did'].split(':')[-1][:8]
    print(f"  Agent ID: ...{did_short}")
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
    print(f"  Chain integrity {'✅ 100%' if chain_i >= 0.999 else f'⚠️ {chain_i*100:.0f}%'}")
    print(f"  Avg latency     {signals['avg_latency_ms']}ms")
    print()
    server_url = get_api_url()
    if server_url:
        print(f"  Full profile: {server_url.replace('/v1', '')}  (register to publish)")
    else:
        print("  Run 'atlast register' to publish your profile to an ECP server")
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
    """atlast flush [--endpoint URL] [--key ak_live_xxx] — force Merkle batch upload now

    Options:
      --endpoint URL   Override server URL
      --key KEY        Agent API key (from 'atlast register')

    Environment:
      ATLAST_API_URL   Default server URL
      ATLAST_ECP_DIR   Custom storage directory
    """
    if "--help" in args or "-h" in args:
        print(cmd_flush.__doc__)
        return

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

    from .batch import _load_batch_state, _save_batch_state

    if resolved_key:
        state = _load_batch_state()
        state["agent_api_key"] = resolved_key
        _save_batch_state(state)

    target = endpoint or get_api_url()
    print(f"⏫ Triggering Merkle batch upload → {target}")

    from .batch import run_batch
    result = run_batch(flush=True)

    if result is None:
        print("ℹ️  No records to upload.")
    elif result.get("uploaded"):
        batch_id = result.get("attestation_uid") or result.get("batch_id") or "—"
        print("✅ Uploaded successfully!")
        print(f"   Attestation: {batch_id}")
        print(f"   Merkle root: {result.get('merkle_root', '')[:50]}...")
        print(f"   Records: {result.get('record_count', 0)}")
    elif result.get("queued"):
        print("⚠️  Upload queued (server unreachable or agent not registered).")
        print(f"   Merkle root: {result.get('merkle_root', '')[:50]}...")
        print(f"   Records: {result.get('record_count', 0)}")
        if not resolved_key:
            print("\n   💡 Tip: Run 'atlast register' first to get an API key.")
            print("           Then: 'atlast flush --key <your_key>'")
    else:
        print(f"❌ Upload failed: {result.get('error', 'unknown')}")
        print("   Records are safely stored locally in ~/.ecp/records/")


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
    # Prefer crypto_pub_key (Ed25519) over legacy pub_key (sha256-based)
    # This ensures the server stores the correct key for signature verification
    pub_key = identity.get("crypto_pub_key") or identity.get("pub_key", "")

    print("\n🔗 Registering Agent...")

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
        print("  Next: Send this claim URL to your owner to activate your profile.")

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
            print("  📁 Local recording continues. Register later with: atlast register")
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

    print("\n📜 Creating Work Certificate")
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
        print("\n  ✅ Certificate issued!")
        print(f"  🆔 {result.get('cert_id')}")
        print(f"  📊 Trust Score: {result.get('trust_score_at_issue')}")
        print(f"  🔗 Verify: {result.get('verify_url')}")
    except Exception as e:
        print(f"\n  ⚠️  Certificate creation failed: {e}")
        print("  📁 Local records are intact. Try again later.")
    print()


def cmd_init(args: list[str]):
    """atlast init [--minimal] [--non-interactive] [--upgrade] — initialize ~/.ecp/ + generate DID

    Options:
      --minimal           Skip identity generation
      --non-interactive   No prompts (CI-friendly)
      --upgrade           Upgrade fallback identity to Ed25519 (if crypto libs available)

    Environment:
      ATLAST_ECP_DIR      Custom storage directory (default: ~/.ecp)
    """
    if "--help" in args or "-h" in args:
        print(cmd_init.__doc__)
        return

    from .storage import init_storage, ECP_DIR
    init_storage()

    skip_identity = "--minimal" in args or "--no-identity" in args
    non_interactive = "--non-interactive" in args or not sys.stdin.isatty()
    do_upgrade = "--upgrade" in args

    print("\n🔗 ATLAST ECP initialized")
    print(f"  Storage: {ECP_DIR}/records/ (local, private)")

    if not skip_identity:
        from .identity import get_or_create_identity
        identity = get_or_create_identity()

        # Handle --upgrade: regenerate Ed25519 identity if currently fallback
        if do_upgrade and not identity.get("verified"):
            try:
                from nacl.signing import SigningKey
                import json
                import stat
                sk = SigningKey.generate()
                pub = sk.verify_key.encode().hex()
                priv = sk.encode().hex()
                old_did = identity.get("did", "")
                identity["pub_key"] = pub
                identity["priv_key"] = priv
                identity["verified"] = True
                # Write back
                id_file = ECP_DIR / "identity.json"
                id_file.write_text(json.dumps(identity, indent=2))
                try:
                    id_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass
                print(f"  ⬆️  Upgraded to Ed25519! (DID unchanged: {old_did})")
            except ImportError:
                print("  ⚠️  Cannot upgrade: install PyNaCl first (pip install pynacl)")

        # Show identity info — friendly for non-technical users
        did_short = identity['did'].split(':')[-1][:8]  # first 8 chars
        is_ed25519 = identity.get('verified', False)
        print(f"  Identity: ✅ created (ID: ...{did_short})")
        if not is_ed25519:
            # Silently try to auto-upgrade to Ed25519
            try:
                from nacl.signing import SigningKey
                import stat
                sk = SigningKey.generate()
                identity["pub_key"] = sk.verify_key.encode().hex()
                identity["priv_key"] = sk.encode().hex()
                identity["verified"] = True
                id_file = ECP_DIR / "identity.json"
                id_file.write_text(json.dumps(identity, indent=2))
                try:
                    id_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass
                print("  Security: ✅ Ed25519 (strong)")
            except ImportError:
                print("  Security: ✅ ready (upgrade with: pip install pynacl)")

        else:
            print("  Security: ✅ Ed25519 (strong)")

        # Show recovery phrase for NEW identities
        mnemonic = identity.get("_mnemonic")
        if mnemonic:
            from .recovery import format_mnemonic_display
            print("\n  🔑 RECOVERY PHRASE — write this down and store safely:")
            for line in format_mnemonic_display(mnemonic).split("\n"):
                print(f"  {line}")
            print("\n  ⚠️  This is the ONLY way to recover your identity if lost.")
            print("  ⚠️  It will NOT be shown again.\n")

        # Ask for vault backup location
        if not non_interactive and mnemonic:
            _ask_backup_location()

        # Auto-register with server (silent on failure)
        try:
            _auto_register(identity)
            print("  Server: ✅ registered")
        except Exception:
            print("  Server: 📁 offline mode (records saved locally, sync later with: atlast register)")

        print("\n  ✅ All set! Your agent's work is now being recorded.")
        print("     Use your agent normally — evidence is captured automatically.")
    else:
        print("  Identity: skipped (run 'atlast init' to create DID)")
        print("\n  Next: echo '{\"in\":\"prompt\",\"out\":\"response\"}' | atlast record")
    print()


def _ask_backup_location():
    """Interactive prompt to choose vault backup location."""
    from .vault_backup import detect_backup_locations
    from .config import save_config

    locations = detect_backup_locations()
    available = [loc for loc in locations if loc["available"]]

    print("  📁 Where should evidence content be backed up?")
    print("     (Encrypted backup ensures recovery if this computer is lost)\n")

    for i, loc in enumerate(available):
        print(f"     [{i + 1}] {loc['name']:<16} ({loc['path']})")
    print(f"     [{len(available) + 1}] Custom path")
    print(f"     [{len(available) + 2}] Skip (not recommended)")

    try:
        choice = input("\n  > ").strip()
        idx = int(choice) - 1

        if idx < len(available):
            path = available[idx]["path"]
        elif idx == len(available):
            path = input("  Enter path: ").strip()
            if not path:
                print("  ⏭  Skipped. Set later: atlast config set vault_backup_path /your/path")
                return
        else:
            print("  ⏭  Skipped. Set later: atlast config set vault_backup_path /your/path")
            return

        save_config({"vault_backup_path": path})
        print(f"\n  ✅ Vault backup: {path} (AES-256-GCM encrypted)")
    except (ValueError, EOFError, KeyboardInterrupt):
        print("\n  ⏭  Skipped. Set later: atlast config set vault_backup_path /your/path")


def _auto_register(identity: dict):
    """Auto-register agent with ATLAST server during init."""
    import urllib.request
    from .config import get_api_url, save_config

    server_url = get_api_url()
    did = identity["did"]
    pub_key = identity.get("crypto_pub_key") or identity["pub_key"]

    payload = json.dumps({"did": did, "public_key": pub_key}).encode()
    req = urllib.request.Request(
        f"{server_url}/agents/register",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            api_key = data.get("api_key") or data.get("key")
            if api_key:
                save_config({"agent_api_key": api_key, "agent_did": did, "endpoint": server_url})
                print(f"  ✅ Registered: {did}")
                print(f"  🔑 API Key: {api_key[:12]}...{api_key[-4:]} (saved to config)")
    except Exception as e:
        error_str = str(e)
        if "409" in error_str:
            print(f"  ✓ Already registered: {did}")
            save_config({"agent_did": did, "endpoint": server_url})
        else:
            raise


def cmd_recover(args: list[str]):
    """atlast recover — restore identity from 12-word recovery phrase"""
    from .recovery import mnemonic_to_entropy, entropy_to_ed25519_seed
    from .storage import init_storage

    print("\n🔄 ATLAST Identity Recovery\n")

    # Get mnemonic
    if args:
        words = " ".join(args).lower().split()
    else:
        try:
            phrase = input("  Enter your 12-word recovery phrase:\n  > ").strip()
            words = phrase.lower().split()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return

    if len(words) != 12:
        print(f"  ❌ Expected 12 words, got {len(words)}")
        return

    # Try BIP39 → HKDF path (new identities)
    try:
        from .recovery import mnemonic_to_entropy, entropy_to_ed25519_seed
        entropy = mnemonic_to_entropy(words)
    except ValueError as e:
        print(f"  ❌ Invalid mnemonic: {e}")
        return

    seed = entropy_to_ed25519_seed(entropy)

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
    except ImportError:
        print("  ❌ cryptography package required. pip install cryptography")
        return

    import hashlib
    key = Ed25519PrivateKey.from_private_bytes(seed)
    pub_hex = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    priv_hex = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    did = f"did:ecp:{hashlib.sha256(pub_hex.encode()).hexdigest()[:32]}"

    # Also try legacy path (first 16 bytes as direct key)

    print(f"  ✅ Identity recovered: {did}")

    # Save identity
    init_storage()
    from .identity import _resolve_ecp_dir, _now_ms
    edir = _resolve_ecp_dir()
    edir.mkdir(parents=True, exist_ok=True)

    identity = {
        "did": did,
        "pub_key": pub_hex,
        "priv_key": priv_hex,
        "created_at": _now_ms(),
        "verified": True,
        "recovery_version": 1,
        "entropy_hash": hashlib.sha256(entropy).hexdigest()[:32],
        "recovered_at": _now_ms(),
    }

    ifile = edir / "identity.json"
    ifile.write_text(json.dumps(identity, indent=2))
    print(f"  ✅ Identity saved to {ifile}")

    # Try to pull records from server
    print("\n  🔄 Syncing records from server...")
    try:
        _sync_records_from_server(did, identity)
    except Exception as e:
        print(f"  ⚠️  Could not sync from server: {e}")
        print("  📁 Local identity restored. Records can be synced later.")

    # Try vault restore
    from .config import get_vault_backup_path
    backup_path = get_vault_backup_path()
    if backup_path:
        print(f"\n  🔄 Restoring vault from {backup_path}...")
        try:
            from .vault_backup import restore_vault_entries
            restored, errors = restore_vault_entries(backup_path, priv_hex)
            print(f"  ✅ Vault restored: {restored} entries ({errors} errors)")
        except Exception as e:
            print(f"  ⚠️  Vault restore failed: {e}")

    print("\n  ✅ Recovery complete. You can continue recording.\n")


def _sync_records_from_server(did: str, identity: dict):
    """Pull records from server for this DID."""
    import urllib.request
    from .config import get_api_url, get_api_key

    server_url = get_api_url()
    api_key = get_api_key()

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    url = f"{server_url}/agents/{did}/records?limit=10000"
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            records = data.get("records", [])

            if not records:
                print(f"  ℹ️  No records found on server for {did}")
                return

            from .storage import ECP_DIR
            records_dir = ECP_DIR / "records"
            records_dir.mkdir(parents=True, exist_ok=True)

            saved = 0
            for rec in records:
                rid = rec.get("id") or rec.get("record_id", f"rec_{saved}")
                rfile = records_dir / f"{rid}.json"
                if not rfile.exists():
                    rfile.write_text(json.dumps(rec, indent=2))
                    saved += 1

            print(f"  ✅ Downloaded {saved} new records ({len(records)} total on server)")
    except Exception as e:
        if "404" in str(e):
            print("  ℹ️  Server endpoint not available yet (records sync coming soon)")
        else:
            raise


def cmd_backup_key(args: list[str]):
    """atlast backup-key — display recovery phrase for current identity"""
    from .identity import get_or_create_identity
    from .recovery import export_mnemonic_for_legacy_key, format_mnemonic_display

    identity = get_or_create_identity()
    priv_hex = identity.get("priv_key")

    if not priv_hex:
        print("  ❌ No private key found in identity.")
        return

    print("\n  ⚠️  This will display your secret recovery phrase.")
    print("  ⚠️  Anyone with these words can control your agent identity.\n")

    if sys.stdin.isatty():
        try:
            confirm = input("  Type 'yes' to continue: ").strip()
            if confirm.lower() != "yes":
                print("  Cancelled.")
                return
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return

    # Check if this is a BIP39-derived identity or legacy
    if identity.get("recovery_version") == 1:
        # New identity: we need to regenerate mnemonic from entropy
        # But we don't store entropy... we store entropy_hash for verification
        # For new identities, we can derive mnemonic from private key
        # by reversing: priv_key → seed, but HKDF is one-way
        # So for new identities created with BIP39, the mnemonic was shown at init only
        print("\n  ℹ️  This identity was created with recovery phrase support.")
        print("  ℹ️  The phrase was shown during 'atlast init'.")
        print("  ℹ️  If you lost it, you'll need to create a new identity.\n")
        print("  💡 For legacy identities, we can export a recovery phrase.")
        return

    # Legacy identity: export from private key
    words = export_mnemonic_for_legacy_key(priv_hex)

    print(f"\n  🔑 RECOVERY PHRASE for {identity['did']}:")
    for line in format_mnemonic_display(words).split("\n"):
        print(f"  {line}")
    print("\n  ⚠️  LEGACY KEY: This phrase encodes the first 16 bytes of your private key.")
    print("  ⚠️  Recovery will recreate a compatible identity.\n")


def cmd_backup(args: list[str]):
    """atlast backup [--vault] [--path /dir] — backup vault to encrypted storage"""
    from .identity import get_or_create_identity
    from .config import get_vault_backup_path

    path = None
    for i, a in enumerate(args):
        if a == "--path" and i + 1 < len(args):
            path = args[i + 1]

    if not path:
        path = get_vault_backup_path()

    if not path:
        print("  ❌ No backup path. Use --path or: atlast config set vault_backup_path /your/path")
        return

    identity = get_or_create_identity()
    priv_key = identity.get("priv_key")
    if not priv_key:
        print("  ❌ No private key found.")
        return

    print(f"\n  📦 Backing up vault to {path}...")
    from .vault_backup import backup_all_vault
    backed, errors = backup_all_vault(backup_path=path, priv_key_hex=priv_key)
    print(f"  ✅ Backed up {backed} entries ({errors} errors)")

    if errors == 0:
        from .config import save_config
        save_config({"vault_backup_path": path})
        print("  ✅ Backup path saved to config\n")
    else:
        print(f"  ⚠️  {errors} entries failed to backup\n")


def cmd_record(args: list[str]):
    """atlast record — create an ECP record from stdin or flags"""
    from .record import create_minimal_record, create_record
    from .storage import save_record

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
    """atlast push [--endpoint URL] [--key KEY] [--retry] — upload records to ECP server

    --retry  Re-upload previously failed batches from the upload queue.
    """
    if "--retry" in args:
        args_clean = [a for a in args if a != "--retry"]
        # Set endpoint/key if provided
        import os
        for i, a in enumerate(args_clean):
            if a == "--endpoint" and i + 1 < len(args_clean):
                os.environ["ATLAST_API_URL"] = args_clean[i + 1]
            if a == "--key" and i + 1 < len(args_clean):
                from .batch import _load_batch_state, _save_batch_state
                state = _load_batch_state()
                state["agent_api_key"] = args_clean[i + 1]
                _save_batch_state(state)

        from .batch import _retry_queued, get_upload_queue
        queue = get_upload_queue()
        if not queue:
            print("✅ No failed batches in queue.")
            return
        print(f"🔄 Retrying {len(queue)} failed batch(es)...")
        _retry_queued()
        remaining = get_upload_queue()
        if not remaining:
            print("✅ All retries succeeded!")
        else:
            print(f"⚠️  {len(remaining)} batch(es) still failing.")
        return

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
        print("Error: aiohttp required for zero-code proxy.")
        print("")
        print("  Install with:  pip install atlast-ecp[proxy]")
        print("  Or install all: pip install atlast-ecp[all]")
        print("")
        print("  Alternative (no extra install):")
        print("    from atlast_ecp import wrap")
        print("    client = wrap(openai.OpenAI())  # 1 line, zero deps")
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
        print("Error: aiohttp required for 'atlast run'.")
        print("")
        print("  Install with:  pip install atlast-ecp[proxy]")
        print("  Or install all: pip install atlast-ecp[all]")
        print("")
        print("  Alternative (no extra install):")
        print("    from atlast_ecp import wrap")
        print("    client = wrap(openai.OpenAI())  # 1 line, zero deps")
        sys.exit(1)


def _cmd_insights(args: list[str]):
    """atlast insights [--json] [--top N] [--limit N] — analyze ECP records"""
    from .insights import cmd_insights
    cmd_insights(args)


def cmd_proof(args: list[str]):
    """atlast proof [--session ID] [--include-content] [--records id1,id2] [-o file.json]"""
    from .proof import generate_proof, verify_proof, format_proof_report

    session_id = None
    include_content = "--include-content" in args or "-c" in args
    output_file = None
    record_ids = None

    for i, a in enumerate(args):
        if a == "--session" and i + 1 < len(args):
            session_id = args[i + 1]
        if (a == "-o" or a == "--output") and i + 1 < len(args):
            output_file = args[i + 1]
        if a == "--records" and i + 1 < len(args):
            record_ids = args[i + 1].split(",")

    proof = generate_proof(
        record_ids=record_ids,
        session_id=session_id,
        include_content=include_content,
    )

    if "error" in proof:
        print(f"❌ {proof['error']}")
        sys.exit(1)

    # Self-verify
    verification = verify_proof(proof)

    if output_file:
        with open(output_file, "w") as f:
            json.dump(proof, f, indent=2, ensure_ascii=False)
        print(f"✅ Proof package saved: {output_file}")
        print(f"   Records: {proof['summary']['total_records']}")
        print(f"   Content: {proof['summary']['content_included']} included, "
              f"{proof['summary']['content_redacted']} redacted")
        print(f"   Verification: {'✅ VALID' if verification['valid'] else '❌ ISSUES'}")
        print("\n   Share this file. Recipient verifies with:")
        print(f"   $ atlast verify --proof {output_file}")
    else:
        print(format_proof_report(proof, verification))


def cmd_inspect(args: list[str]):
    """atlast inspect <record_id> — show record with full content + hash verification"""
    if not args:
        print("Usage: atlast inspect <record_id>")
        print("  Shows the ECP record paired with original content from the local vault.")
        print("  Verifies that content hashes match the record.")
        sys.exit(1)

    record_id = args[0]
    from .storage import load_record_by_id, load_vault
    from .record import hash_content

    record = load_record_by_id(record_id)
    if not record:
        print(f"❌ Record not found: {record_id}")
        sys.exit(1)

    vault = load_vault(record_id)

    # Extract hashes from record
    if record.get("ecp") == "1.0":
        in_hash = record.get("in_hash", "")
        out_hash = record.get("out_hash", "")
        meta = record.get("meta", {})
        action = record.get("action", "?")
        model = meta.get("model", "—")
        latency = meta.get("latency_ms", 0)
        tokens_in = meta.get("tokens_in", "—")
        tokens_out = meta.get("tokens_out", "—")
        flags = meta.get("flags", [])
        session = meta.get("session_id", "—")
    else:
        step = record.get("step", {})
        in_hash = step.get("in_hash", "")
        out_hash = step.get("out_hash", "")
        action = step.get("type", "?")
        model = step.get("model", "—")
        latency = step.get("latency_ms", 0)
        tokens_in = step.get("tokens_in", "—")
        tokens_out = step.get("tokens_out", "—")
        flags = step.get("flags", [])
        session = step.get("session_id", "—")

    chain = record.get("chain", {})
    ts = record.get("ts", 0)

    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "?"

    print(f"\n🔍 ECP Record Inspection: {record_id}")
    print("=" * 60)
    print(f"  Time:     {dt}")
    print(f"  Agent:    {record.get('agent', '?')}")
    print(f"  Session:  {session}")
    print(f"  Action:   {action}")
    print(f"  Model:    {model}")
    print(f"  Latency:  {latency}ms")
    print(f"  Tokens:   {tokens_in} in / {tokens_out} out")
    print(f"  Flags:    {flags if flags else '✅ clean'}")

    # Chain info
    if chain:
        print("\n🔗 Chain")
        print(f"  Prev:     {chain.get('prev', '?')}")
        print(f"  Hash:     {chain.get('hash', '?')[:40]}...")
        print(f"  Sig:      {record.get('sig', 'none')[:40]}...")

    # Content + Hash verification
    print("\n📄 Content (from local vault)")
    print("-" * 60)

    if not vault:
        print("  ⚠️  No vault content found for this record.")
        print("  Content vault was not enabled when this record was created.")
        print("  Hashes are still valid — but original content is not available.")
        print(f"\n  in_hash:  {in_hash}")
        print(f"  out_hash: {out_hash}")
    else:
        input_text = vault.get("input", "")
        output_text = vault.get("output", "")

        # Verify hashes match
        computed_in_hash = hash_content(input_text)
        computed_out_hash = hash_content(output_text)
        in_match = computed_in_hash == in_hash
        out_match = computed_out_hash == out_hash

        print(f"\n  📥 INPUT {'✅ hash verified' if in_match else '❌ HASH MISMATCH'}")
        print(f"  Hash: {in_hash}")
        print(f"  ┌{'─'*56}┐")
        # Truncate long content
        display_in = input_text[:500] + ("..." if len(input_text) > 500 else "")
        for line in display_in.split("\n"):
            print(f"  │ {line[:54]:54s} │")
        print(f"  └{'─'*56}┘")

        print(f"\n  📤 OUTPUT {'✅ hash verified' if out_match else '❌ HASH MISMATCH'}")
        print(f"  Hash: {out_hash}")
        print(f"  ┌{'─'*56}┐")
        display_out = output_text[:800] + ("..." if len(output_text) > 800 else "")
        for line in display_out.split("\n"):
            print(f"  │ {line[:54]:54s} │")
        print(f"  └{'─'*56}┘")

        if in_match and out_match:
            print("\n  🟢 CONTENT VERIFIED — hashes match original content")
            print("     sha256(input)  == record.in_hash  ✅")
            print("     sha256(output) == record.out_hash ✅")
            print("     Content has NOT been tampered with.")
        else:
            print("\n  🔴 CONTENT MISMATCH — content may have been altered!")
            if not in_match:
                print("     sha256(input)  != record.in_hash  ❌")
            if not out_match:
                print("     sha256(output) != record.out_hash ❌")

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

    endpoints = data.get("endpoints", {})
    if endpoints:
        if isinstance(endpoints, dict):
            print(f"\n  Endpoints ({len(endpoints)}):")
            for name, path in endpoints.items():
                print(f"    {name:20s} {path}")
        elif isinstance(endpoints, list):
            print(f"\n  Endpoints ({len(endpoints)}):")
            for ep in endpoints:
                if isinstance(ep, dict):
                    print(f"    {ep.get('method', '?'):6s} {ep.get('path', '?')}")
                else:
                    print(f"    {ep}")

    auth = data.get("auth_methods", [])
    if auth:
        print(f"\n  Auth: {', '.join(auth)}")

    chain = data.get("chain")
    if chain:
        print(f"\n  Chain: {chain}")

    print()


# ── Query & Audit Commands ────────────────────────────────────────────────────


def cmd_search(args: list[str]):
    """atlast search <query> [--agent DID] [--since DATE] [--until DATE] [--errors] [--json] [--limit N]"""
    import json as _json
    if not args:
        print("Usage: atlast search <query> [--agent DID] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--errors] [--json]")
        return

    query = []
    agent = None
    since = None
    until = None
    errors_only = False
    as_json = False
    limit = 20
    i = 0
    while i < len(args):
        if args[i] == "--agent" and i + 1 < len(args):
            agent = args[i + 1]
            i += 2
        elif args[i] == "--since" and i + 1 < len(args):
            since = args[i + 1]
            i += 2
        elif args[i] == "--until" and i + 1 < len(args):
            until = args[i + 1]
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "--errors":
            errors_only = True
            i += 1
        elif args[i] == "--json":
            as_json = True
            i += 1
        else:
            query.append(args[i])
            i += 1

    from .query import search
    results = search(" ".join(query), limit=limit, agent=agent, since=since, until=until, errors_only=errors_only, as_json=as_json)
    if as_json:
        print(_json.dumps(results, indent=2, default=str))


def cmd_trace(args: list[str]):
    """atlast trace <record_id> [--forward] [--limit N] [--json]"""
    import json as _json
    if not args:
        print("Usage: atlast trace <record_id> [--forward] [--limit N] [--json]")
        return

    record_id = args[0]
    direction = "back"
    limit = 50
    as_json = False
    for i, a in enumerate(args[1:], 1):
        if a == "--forward":
            direction = "forward"
        elif a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        elif a == "--json":
            as_json = True

    from .query import trace
    chain = trace(record_id, direction=direction, limit=limit, as_json=as_json)
    if as_json:
        print(_json.dumps(chain, indent=2, default=str))


def cmd_audit(args: list[str]):
    """atlast audit [--days N] [--agent DID] [--json]"""
    import json as _json
    days = 30
    agent = None
    as_json = False
    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
            i += 2
        elif args[i] == "--agent" and i + 1 < len(args):
            agent = args[i + 1]
            i += 2
        elif args[i] == "--json":
            as_json = True
            i += 1
        elif args[i] == "--last" and i + 1 < len(args):
            # --last 60d format
            val = args[i + 1]
            if val.endswith("d"):
                days = int(val[:-1])
            i += 2
        else:
            i += 1

    from .query import audit
    report = audit(days=days, agent=agent, as_json=as_json)
    if as_json:
        print(_json.dumps(report, indent=2, default=str))


def cmd_timeline(args: list[str]):
    """atlast timeline [--days N] [--since DATE] [--until DATE] [--agent DID] [--json]"""
    import json as _json
    days = 7
    since = None
    until = None
    agent = None
    as_json = False
    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
            i += 2
        elif args[i] == "--since" and i + 1 < len(args):
            since = args[i + 1]
            i += 2
        elif args[i] == "--until" and i + 1 < len(args):
            until = args[i + 1]
            i += 2
        elif args[i] == "--agent" and i + 1 < len(args):
            agent = args[i + 1]
            i += 2
        elif args[i] == "--json":
            as_json = True
            i += 1
        else:
            i += 1

    from .query import timeline
    results = timeline(days=days, since=since, until=until, agent=agent, as_json=as_json)
    if as_json:
        print(_json.dumps(results, indent=2, default=str))


def cmd_index(args: list[str]):
    """atlast index — rebuild search index"""
    from .query import rebuild_index
    print("🔄 Rebuilding search index...")
    count = rebuild_index(verbose=True)
    print(f"✅ Index built: {count} records")


def cmd_demo(args: list[str]):
    """atlast demo [--days 60] — generate realistic demo data for dashboard"""
    days = 60
    for i, a in enumerate(args):
        if a == "--days" and i + 1 < len(args):
            days = int(args[i + 1])

    from .demo_data import generate_demo_data
    print(f"🎲 Generating {days} days of realistic demo data...")
    count = generate_demo_data(days=days)
    print(f"✅ Generated {count} records across {days} days")
    print("   Agent: did:ecp:demo_research_agent_001")
    print("   Scenario: Market research agent with drift + error spike around day 30-34")
    print("\n   Now run: atlast dashboard")


def cmd_doctor(args: list[str]):
    """atlast doctor — diagnose environment and auto-fix common issues"""
    import shutil
    from pathlib import Path

    print("\n🩺 ATLAST Doctor — checking your environment...\n")
    issues = []
    fixed = []
    all_ok = True

    # 1. Python version
    v = sys.version_info
    if v >= (3, 9):
        print(f"  ✅ Python {v.major}.{v.minor}.{v.micro}")
    else:
        print(f"  ❌ Python {v.major}.{v.minor}.{v.micro} — need 3.9+")
        issues.append("Upgrade Python to 3.9 or later")
        all_ok = False

    # 2. atlast-ecp installed
    try:
        from atlast_ecp import __version__ as ver
        print(f"  ✅ atlast-ecp {ver}")
    except ImportError:
        print("  ❌ atlast-ecp not installed")
        issues.append("Run: pip install atlast-ecp")
        all_ok = False

    # 3. ECP directory
    from .storage import ECP_DIR
    if ECP_DIR.exists():
        print(f"  ✅ Storage: {ECP_DIR}")
    else:
        print(f"  ⚠️  Storage not initialized — fixing...")
        try:
            from .storage import init_storage
            init_storage()
            print(f"  ✅ Storage: {ECP_DIR} (just created)")
            fixed.append("Created ~/.ecp/ directory")
        except Exception as e:
            print(f"  ❌ Cannot create {ECP_DIR}: {e}")
            issues.append(f"Cannot create {ECP_DIR}")
            all_ok = False

    # 4. Identity
    id_file = ECP_DIR / "identity.json"
    if id_file.exists():
        try:
            identity = json.loads(id_file.read_text())
            did_short = identity.get("did", "?").split(":")[-1][:8]
            is_ed25519 = identity.get("verified", False)
            print(f"  ✅ Identity: ...{did_short} ({'Ed25519' if is_ed25519 else 'fallback'})")

            # Auto-upgrade to Ed25519 if possible
            if not is_ed25519:
                try:
                    from nacl.signing import SigningKey
                    import stat
                    sk = SigningKey.generate()
                    identity["pub_key"] = sk.verify_key.encode().hex()
                    identity["priv_key"] = sk.encode().hex()
                    identity["verified"] = True
                    id_file.write_text(json.dumps(identity, indent=2))
                    try:
                        id_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
                    except OSError:
                        pass
                    print(f"  ✅ Auto-upgraded to Ed25519!")
                    fixed.append("Upgraded identity to Ed25519")
                except ImportError:
                    pass  # PyNaCl not available, fallback is fine
        except Exception:
            print("  ❌ Identity file corrupted")
            issues.append("Delete ~/.ecp/identity.json and run: atlast init")
            all_ok = False
    else:
        print("  ⚠️  No identity — fixing...")
        try:
            from .identity import get_or_create_identity
            identity = get_or_create_identity()
            did_short = identity.get("did", "?").split(":")[-1][:8]
            print(f"  ✅ Identity: ...{did_short} (just created)")
            fixed.append("Created new identity")
        except Exception as e:
            print(f"  ❌ Cannot create identity: {e}")
            issues.append("Run: atlast init")
            all_ok = False

    # 5. PyNaCl (Ed25519 signatures)
    try:
        import nacl
        print(f"  ✅ PyNaCl {nacl.__version__} (strong signatures)")
    except ImportError:
        print("  ⚠️  PyNaCl not installed (optional, for stronger signatures)")
        if "--fix" in args:
            print("     Installing PyNaCl...")
            import subprocess
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pynacl", "-q"])
                print("  ✅ PyNaCl installed!")
                fixed.append("Installed PyNaCl")
            except Exception:
                print("  ⚠️  Could not auto-install PyNaCl (not critical)")

    # 6. Server connectivity
    try:
        from .config import get_api_url
        server_url = get_api_url()
        import urllib.request
        req = urllib.request.Request(f"{server_url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"  ✅ Server: {server_url} (online)")
    except Exception:
        print(f"  ⚠️  Server: offline (not critical — records are saved locally)")

    # 7. Records count
    records_dir = ECP_DIR / "records"
    if records_dir.exists():
        count = len(list(records_dir.glob("*.json")))
        print(f"  ✅ Records: {count}")
    else:
        print("  ✅ Records: 0 (ready to start)")

    # 8. Disk space
    try:
        usage = shutil.disk_usage(str(ECP_DIR))
        free_gb = usage.free / (1024**3)
        if free_gb > 1:
            print(f"  ✅ Disk: {free_gb:.1f} GB free")
        else:
            print(f"  ⚠️  Disk: only {free_gb:.2f} GB free")
            if free_gb < 0.1:
                issues.append("Disk almost full — free up space")
                all_ok = False
    except Exception:
        pass

    # Summary
    print()
    if fixed:
        print(f"  🔧 Auto-fixed {len(fixed)} issue(s):")
        for f in fixed:
            print(f"     • {f}")
        print()

    if all_ok and not issues:
        print("  ✅ All good! Your agent is ready to record evidence.\n")
    elif issues:
        print(f"  ❌ {len(issues)} issue(s) need attention:")
        for i in issues:
            print(f"     • {i}")
        print()
        if "--fix" not in args:
            print("  💡 Run 'atlast doctor --fix' to auto-fix what's possible.\n")


def cmd_dashboard(args: list[str]):
    """atlast dashboard [--port 3827] [--no-open] — launch local web dashboard"""
    port = 3827
    open_browser = True
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == "--no-open":
            open_browser = False
            i += 1
        else:
            i += 1

    from .dashboard_server import start_dashboard
    start_dashboard(port=port, open_browser=open_browser)


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
        print("  Query & Audit:")
        print("    atlast search <query>    Search records (full-text)")
        print("    atlast trace <id>        Trace evidence chain (root cause)")
        print("    atlast audit [--days N]  Automated audit report")
        print("    atlast timeline          Daily activity timeline")
        print("    atlast index             Rebuild search index")
        print("    atlast dashboard         Open local web dashboard")
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
        print("  Recovery & Backup:")
        print("    atlast recover           Restore identity from recovery phrase")
        print("    atlast backup-key        Show recovery phrase for current identity")
        print("    atlast backup [--path p] Backup vault to encrypted storage")
        print()
        print("  Diagnostics:")
        print("    atlast doctor            Check environment & auto-fix issues")
        print("    atlast doctor --fix      Auto-fix + install optional deps")
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
        "inspect": cmd_inspect,
        "proof": cmd_proof,
        "insights": _cmd_insights,
        "config": _cmd_config,
        "discover": _cmd_discover,
        "recover": cmd_recover,
        "backup-key": cmd_backup_key,
        "backup": cmd_backup,
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

    # Query & Audit commands (dynamic import to avoid circular)
    query_commands = {
        "search": cmd_search,
        "trace": cmd_trace,
        "audit": cmd_audit,
        "timeline": cmd_timeline,
        "index": cmd_index,
        "dashboard": cmd_dashboard,
        "doctor": cmd_doctor,
        "demo": cmd_demo,
    }
    commands.update(query_commands)

    if cmd in commands:
        commands[cmd](rest)
    else:
        print(f"Unknown command: {cmd}")
        print("Run 'atlast' or 'atlast --help' for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
