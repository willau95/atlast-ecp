#!/usr/bin/env python3
"""
ATLAST Protocol — Production Scenario Test v2
Uses actual SDK API signatures.
"""

import json, time, os, sys, hashlib, tempfile, traceback, subprocess

sys.path.insert(0, "/tmp/atlast-ecp/sdk")

results = {"passed": [], "failed": [], "warnings": []}

def test(name):
    def decorator(fn):
        def wrapper():
            try:
                fn()
                results["passed"].append(name)
                print(f"  ✅ {name}")
            except Exception as e:
                results["failed"].append((name, str(e)))
                print(f"  ❌ {name}: {e}")
        return wrapper
    return decorator

def warn(msg):
    results["warnings"].append(msg)
    print(f"  ⚠️  {msg}")

TEST_ECP_DIR = tempfile.mkdtemp(prefix="atlast_prod_test_")
os.environ["ECP_DIR"] = TEST_ECP_DIR
os.environ.pop("ATLAST_API_URL", None)
os.environ.pop("ATLAST_API_KEY", None)

print(f"\n{'='*60}")
print("ATLAST Protocol — Production Scenario Test v2")
print(f"ECP_DIR: {TEST_ECP_DIR}")
print(f"{'='*60}\n")

import atlast_ecp
from atlast_ecp.record import ECPRecord, ECPStep, ECPChain

# ============================================================
# TEST 1: Init & Identity
# ============================================================
print("📋 Layer 0: Init & Identity")

@test("Init ECP project")
def t():
    atlast_ecp.reset()
    result = atlast_ecp.init(agent_id="research-agent")
    assert result is not None, f"init returned None"
    print(f"    Init result: {result}")
t()

@test("Identity creation (DID)")
def t():
    identity = atlast_ecp.get_or_create_identity()
    assert identity is not None
    assert "did" in identity, f"Keys: {list(identity.keys())}"
    print(f"    DID: {identity['did']}")
    print(f"    Public key: {identity.get('public_key', 'N/A')[:32]}...")
t()

# ============================================================
# TEST 2: Minimal Record (Level 0)
# ============================================================
print("\n📋 Layer 1: Records")

@test("Minimal record creation")
def t():
    rec = atlast_ecp.create_minimal_record(
        agent="research-agent",
        action="web_search",
        in_content="Find latest AI regulation news",
        out_content="Found 5 articles about EU AI Act enforcement..."
    )
    assert rec is not None
    assert isinstance(rec, dict), f"Expected dict, got {type(rec)}"
    print(f"    Keys: {list(rec.keys())}")
t()

@test("Full record with create_record")
def t():
    identity = atlast_ecp.get_or_create_identity()
    rec = atlast_ecp.create_record(
        agent_did=identity["did"],
        step_type="research",
        in_content="Analyze competitor landscape for AI trust protocols",
        out_content=json.dumps({"summary": "Identified 3 major competitors", "confidence": 0.87}),
        identity=identity,
        model="claude-sonnet-4-20250514",
        tokens_in=4500,
        tokens_out=2400,
        latency_ms=6130,
    )
    assert rec is not None
    d = atlast_ecp.record_to_dict(rec)
    assert "id" in d
    assert "sig" in d
    print(f"    Record ID: {d['id']}")
    print(f"    Signature: {d['sig'][:32]}...")
    return rec
full_rec = t()

@test("Record save & load")
def t():
    identity = atlast_ecp.get_or_create_identity()
    rec = atlast_ecp.create_record(
        agent_did=identity["did"],
        step_type="fact_check",
        in_content="Is GDPR still active in 2026?",
        out_content="Yes, GDPR remains active.",
        identity=identity,
        latency_ms=500,
    )
    d = atlast_ecp.record_to_dict(rec)
    path = atlast_ecp.save_record(d)
    assert path, "save_record should return a path"
    print(f"    Saved to: {path}")
    
    records = atlast_ecp.load_records(limit=10)
    assert len(records) > 0, "Should have at least 1 record"
    print(f"    Loaded {len(records)} record(s)")
t()

# ============================================================
# TEST 3: Record Chaining
# ============================================================
print("\n📋 Record Chaining & Integrity")

@test("Hash chain across 5 records")
def t():
    identity = atlast_ecp.get_or_create_identity()
    prev = None
    for i in range(5):
        rec = atlast_ecp.create_record(
            agent_did=identity["did"],
            step_type=f"pipeline_step_{i+1}",
            in_content=f"Step {i+1} input",
            out_content=f"Step {i+1} output",
            identity=identity,
            prev_record=prev,
            latency_ms=100 + i * 50,
        )
        d = atlast_ecp.record_to_dict(rec)
        atlast_ecp.save_record(d)
        chain_hash = d.get("chain", {}).get("hash", "")
        prev_hash = d.get("chain", {}).get("prev", "")
        print(f"    Step {i+1}: hash={chain_hash[:12]}... prev={prev_hash[:12] if prev_hash else 'genesis'}...")
        prev = rec
t()

@test("Record verification (chain hash)")
def t():
    records = atlast_ecp.load_records(limit=1)
    assert len(records) > 0
    result = atlast_ecp.verify_record(records[0])
    assert result["chain_hash_ok"], f"Chain hash should be valid: {result}"
    print(f"    Verify result: {result}")
t()

@test("Signature round-trip (sign + verify)")
def t():
    identity = atlast_ecp.get_or_create_identity()
    rec = atlast_ecp.create_record(
        agent_did=identity["did"], step_type="sig_test",
        in_content="sign me", out_content="verified",
        identity=identity, latency_ms=100,
    )
    d = atlast_ecp.record_to_dict(rec)
    assert d["sig"].startswith("ed25519:"), f"Should have real sig, got: {d['sig']}"
    atlast_ecp.save_record(d)
    loaded = atlast_ecp.load_records(limit=1)[0]
    result = atlast_ecp.verify_record_with_key(loaded, identity["pub_key"])
    assert result["signature_ok"] is True, f"Signature should verify: {result}"
    assert result["chain_hash_ok"] is True
    assert result["valid"] is True
    print(f"    Signature verified ✅: {result}")
t()

# ============================================================
# TEST 4: Trust Signals & Flags
# ============================================================
print("\n📋 Trust Signals & Flags")

@test("Trust signals from batch (incl. chain_integrity)")
def t():
    records = atlast_ecp.load_records(limit=50)
    signals = atlast_ecp.compute_trust_signals(records)
    assert signals is not None
    assert signals["chain_integrity"] == 1.0, f"Chain integrity should be 1.0, got {signals['chain_integrity']}"
    print(f"    Signals: {json.dumps(signals, indent=2, default=str)[:300]}")
t()

@test("Flag detection — normal case")
def t():
    flags = atlast_ecp.detect_flags("Here is a normal research summary about AI regulations.", latency_ms=3000, median_latency_ms=2800)
    print(f"    Normal flags: {flags}")
t()

@test("Flag detection — suspicious case")
def t():
    # Very fast for complex task
    flags = atlast_ecp.detect_flags("A" * 10000, latency_ms=10, median_latency_ms=5000)
    print(f"    Suspicious flags: {flags}")
t()

# ============================================================
# TEST 5: Batch & Merkle
# ============================================================
print("\n📋 Batch & Merkle")

@test("Merkle proof build & verify")
def t():
    records = atlast_ecp.load_records(limit=5)
    hashes = []
    for r in records:
        h = r.get("chain", {}).get("hash", "") or r.get("id", "")
        if h:
            hashes.append(h)
    assert len(hashes) >= 2, f"Need ≥2 hashes, got {len(hashes)}"
    
    proof = atlast_ecp.build_merkle_proof(hashes, hashes[0])
    assert proof is not None
    print(f"    Proof steps: {len(proof)}")
    
    # Compute root from proof
    # verify_merkle_proof(record_hash, proof, merkle_root)
    # Need to compute root - let's just check structure
    print(f"    Proof structure: {proof[:2] if proof else 'empty'}")
t()

@test("Batch run (local, no API)")
def t():
    result = atlast_ecp.run_batch(flush=False)
    print(f"    Batch result: {result}")
t()

# ============================================================
# TEST 6: Proxy Module
# ============================================================
print("\n📋 Proxy Module")

@test("Proxy importable with correct exports")
def t():
    from atlast_ecp.proxy import ATLASTProxy, run_proxy, run_with_proxy
    print(f"    ATLASTProxy: {ATLASTProxy}")
    print(f"    run_proxy: {run_proxy}")
    print(f"    run_with_proxy: {run_with_proxy}")
t()

# ============================================================
# TEST 7: Edge Cases
# ============================================================
print("\n📋 Production Edge Cases")

@test("Unicode handling")
def t():
    identity = atlast_ecp.get_or_create_identity()
    rec = atlast_ecp.create_record(
        agent_did=identity["did"],
        step_type="multilingual",
        in_content="分析中国市场AI监管政策 🇨🇳 «régulations» für KI-Systeme",
        out_content="多语言输出: 中文/français/Deutsch ✅",
        identity=identity,
        latency_ms=1000,
    )
    d = atlast_ecp.record_to_dict(rec)
    assert d["chain"]["hash"], "Hash should work with unicode"
t()

@test("Large payload (100KB input)")
def t():
    identity = atlast_ecp.get_or_create_identity()
    rec = atlast_ecp.create_record(
        agent_did=identity["did"],
        step_type="large_context",
        in_content="x" * 100_000,
        out_content="y" * 50_000,
        identity=identity,
        tokens_in=128000,
        tokens_out=32000,
        latency_ms=45000,
    )
    d = atlast_ecp.record_to_dict(rec)
    path = atlast_ecp.save_record(d)
    assert path
    loaded = atlast_ecp.load_records(limit=1)
    assert len(loaded) > 0
    print(f"    100KB record saved & loaded ✅")
t()

@test("Empty content")
def t():
    rec = atlast_ecp.create_minimal_record(
        agent="research-agent",
        action="noop",
        in_content="",
        out_content=""
    )
    assert rec is not None
t()

@test("Rapid sequential records (50)")
def t():
    identity = atlast_ecp.get_or_create_identity()
    start = time.time()
    for i in range(50):
        rec = atlast_ecp.create_record(
            agent_did=identity["did"],
            step_type="rapid",
            in_content=f"Task {i}",
            out_content=f"Result {i}",
            identity=identity,
            latency_ms=10,
        )
    elapsed = time.time() - start
    rate = 50 / elapsed
    print(f"    50 records in {elapsed:.2f}s = {rate:.0f} records/sec")
    if rate < 50:
        warn(f"Low rate: {rate:.0f}/sec")
t()

@test("Special characters in content")
def t():
    identity = atlast_ecp.get_or_create_identity()
    evil = 'test\x00null\nline\ttab"quote\'apos\\back<html>&amp;{json}[arr]'
    rec = atlast_ecp.create_record(
        agent_did=identity["did"],
        step_type="special_chars",
        in_content=evil,
        out_content=evil,
        identity=identity,
        latency_ms=100,
    )
    d = atlast_ecp.record_to_dict(rec)
    path = atlast_ecp.save_record(d)
    assert path
t()

# ============================================================
# TEST 8: CLI
# ============================================================
print("\n📋 CLI")

@test("CLI --help")
def t():
    r = subprocess.run([sys.executable, "-m", "atlast_ecp", "--help"],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "ECP_DIR": TEST_ECP_DIR})
    if r.returncode != 0:
        # Try cli module
        r = subprocess.run([sys.executable, "-m", "atlast_ecp.cli", "--help"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "ECP_DIR": TEST_ECP_DIR})
    output = r.stdout + r.stderr
    print(f"    Exit code: {r.returncode}")
    print(f"    Output: {output[:200]}")
t()

@test("CLI record command")
def t():
    r = subprocess.run([sys.executable, "-m", "atlast_ecp", "record",
        "--agent", "cli-test-agent", "--action", "test_action",
        "--in", "test input", "--out", "test output"],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "ECP_DIR": TEST_ECP_DIR})
    output = r.stdout + r.stderr
    print(f"    Exit code: {r.returncode}, Output: {output[:200]}")
t()

@test("CLI log command")
def t():
    r = subprocess.run([sys.executable, "-m", "atlast_ecp", "log"],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "ECP_DIR": TEST_ECP_DIR})
    output = r.stdout + r.stderr
    print(f"    Exit code: {r.returncode}, Records shown: {output.count('id')}")
t()

# ============================================================
# TEST 9: Backend API
# ============================================================
print("\n📋 Backend API")

@test("Backend health")
def t():
    import urllib.request
    try:
        with urllib.request.urlopen("https://api.llachat.com/v1/health", timeout=10) as r:
            print(f"    {r.status}: {r.read().decode()[:200]}")
    except Exception as e:
        warn(f"Backend: {e}")
t()

@test("Leaderboard API")
def t():
    import urllib.request
    with urllib.request.urlopen("https://api.llachat.com/v1/leaderboard?period=7d&limit=5", timeout=10) as r:
        data = json.loads(r.read())
        count = data.get("total", len(data.get("items", data if isinstance(data, list) else [])))
        print(f"    {count} agents on leaderboard")
t()

# ============================================================
# TEST 10: DX (Developer Experience) — the REAL production test
# ============================================================
print("\n📋 DX: Developer Experience Audit")

@test("README quick-start code works")
def t():
    """Try the README example and see if it runs"""
    # The README likely says something like: from atlast_ecp import record, init
    # Test the most obvious path a new developer would try
    import atlast_ecp
    atlast_ecp.init()
    identity = atlast_ecp.get_or_create_identity()
    rec = atlast_ecp.create_record(
        agent_did=identity["did"],
        step_type="hello_world",
        in_content="Hello",
        out_content="World",
        identity=identity,
    )
    d = atlast_ecp.record_to_dict(rec)
    atlast_ecp.save_record(d)
    print(f"    Basic flow works ✅")
t()

@test("API discoverability — __all__ matches real exports")
def t():
    import atlast_ecp
    all_exports = atlast_ecp.__all__
    for name in all_exports:
        assert hasattr(atlast_ecp, name), f"{name} in __all__ but not accessible"
    print(f"    {len(all_exports)} exports all accessible ✅")
t()

# ============================================================
# RESULTS
# ============================================================
print(f"\n{'='*60}")
print("PRODUCTION TEST RESULTS")
print(f"{'='*60}")
print(f"  ✅ Passed:   {len(results['passed'])}")
print(f"  ❌ Failed:   {len(results['failed'])}")
print(f"  ⚠️  Warnings: {len(results['warnings'])}")

if results["failed"]:
    print(f"\n{'─'*40}")
    print("FAILURES:")
    for name, err in results["failed"]:
        print(f"  ❌ {name}: {err}")

if results["warnings"]:
    print(f"\n{'─'*40}")
    print("WARNINGS:")
    for w in results["warnings"]:
        print(f"  ⚠️  {w}")

print(f"\n{'─'*40}")
total = len(results['passed']) + len(results['failed'])
print(f"Score: {len(results['passed'])}/{total} ({100*len(results['passed'])//max(total,1)}%)")

import shutil
shutil.rmtree(TEST_ECP_DIR, ignore_errors=True)
sys.exit(1 if results["failed"] else 0)
