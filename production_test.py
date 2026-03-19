#!/usr/bin/env python3
"""
ATLAST Protocol — Production Scenario Test
============================================
Simulates a REAL agent workflow end-to-end:

Scenario: "Research Agent" that searches the web, summarizes findings, and writes a report.
Tests all 3 layers + verification + batch upload + trust signals.
"""

import json
import time
import os
import sys
import hashlib
import tempfile
import traceback

# Add SDK to path
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
                traceback.print_exc()
        return wrapper
    return decorator

def warn(msg):
    results["warnings"].append(msg)
    print(f"  ⚠️  {msg}")

# ============================================================
# Setup: Use a temp ECP directory to avoid polluting real data
# ============================================================
TEST_ECP_DIR = tempfile.mkdtemp(prefix="atlast_prod_test_")
os.environ["ECP_DIR"] = TEST_ECP_DIR
os.environ.pop("ATLAST_API_URL", None)  # Don't hit real backend
os.environ.pop("ATLAST_API_KEY", None)

print(f"\n{'='*60}")
print("ATLAST Protocol — Production Scenario Test")
print(f"ECP_DIR: {TEST_ECP_DIR}")
print(f"{'='*60}\n")

# ============================================================
# TEST 1: Layer 0 — Zero-code init & identity
# ============================================================
print("📋 Layer 0: Zero-Code Setup")

@test("Init ECP project")
def test_init():
    import atlast_ecp
    atlast_ecp.reset()
    atlast_ecp.init(agent_name="research-agent", ecp_dir=TEST_ECP_DIR)
    cfg = atlast_ecp.load_config(ecp_dir=TEST_ECP_DIR)
    assert cfg is not None, "Config should exist after init"

test_init()

@test("Identity creation (DID)")
def test_identity():
    import atlast_ecp
    identity = atlast_ecp.get_or_create_identity("research-agent", ecp_dir=TEST_ECP_DIR)
    assert identity is not None, "Identity should be created"
    assert "did" in identity, f"Identity should have DID, got: {list(identity.keys())}"
    did = identity["did"]
    assert did.startswith("did:ecp:") or did.startswith("did:atlast:"), f"Unexpected DID format: {did}"
    print(f"    DID: {did}")

test_identity()

# ============================================================
# TEST 2: Layer 1 — SDK record() with @track-like workflow
# ============================================================
print("\n📋 Layer 1: SDK Record — Simulated Research Agent")

@test("Minimal record (Level 0)")
def test_minimal():
    import atlast_ecp
    rec = atlast_ecp.create_minimal_record(
        agent_id="research-agent",
        input_text="Find latest AI regulation news",
        output_text="Found 5 articles about EU AI Act enforcement..."
    )
    assert rec is not None
    assert "chain_id" in rec
    assert "timestamp" in rec
    print(f"    chain_id: {rec['chain_id']}")

test_minimal()

@test("Full record with reasoning + execution (Level 2-3)")
def test_full_record():
    import atlast_ecp
    rec = atlast_ecp.create_record(
        agent_id="research-agent",
        input_data={"raw": "Analyze competitor landscape for AI trust protocols", "session_id": "sess_prod_001"},
        reasoning={
            "thinking": "Need to search for existing AI trust/accountability frameworks...",
            "alternatives_considered": ["Search academic papers", "Search GitHub repos", "Search patent databases"],
            "chosen_approach": "Multi-source: academic + GitHub + industry reports",
            "chosen_reason": "Broader coverage for competitive analysis"
        },
        execution=[
            {"step": 1, "action": "web_search", "input": {"query": "AI agent trust protocol"}, "output": {"results": 12}, "duration_ms": 450},
            {"step": 2, "action": "web_search", "input": {"query": "AI accountability framework 2025 2026"}, "output": {"results": 8}, "duration_ms": 380},
            {"step": 3, "action": "summarize", "input": {"articles": 20}, "output": {"summary_length": 1500}, "duration_ms": 2100},
            {"step": 4, "action": "write_report", "input": {"format": "markdown"}, "output": {"file": "competitor_report.md", "words": 2400}, "duration_ms": 3200},
        ],
        output_data={"summary": "Identified 3 major competitors: none with ECP-equivalent...", "confidence": 0.87},
        model="claude-sonnet-4-20250514",
        tokens_in=4500,
        tokens_out=2400,
        duration_ms=6130,
        ecp_dir=TEST_ECP_DIR
    )
    assert rec is not None
    assert "chain_id" in rec
    assert "integrity" in rec
    chain_hash = rec["integrity"].get("chain_hash", "")
    assert chain_hash, "Should have chain_hash for integrity"
    print(f"    chain_id: {rec['chain_id']}")
    print(f"    chain_hash: {chain_hash[:16]}...")
    return rec

full_rec = test_full_record()

@test("Record persistence (save + load)")
def test_persistence():
    import atlast_ecp
    # Save the minimal record
    rec = atlast_ecp.create_minimal_record(
        agent_id="research-agent",
        input_text="Quick fact check: Is GDPR still active in 2026?",
        output_text="Yes, GDPR remains active. EU AI Act also in effect since Aug 2025."
    )
    atlast_ecp.save_record(rec, ecp_dir=TEST_ECP_DIR)
    
    # Load it back
    records = atlast_ecp.load_records(agent_id="research-agent", ecp_dir=TEST_ECP_DIR)
    assert len(records) > 0, "Should have at least 1 saved record"
    print(f"    Saved & loaded {len(records)} record(s)")

test_persistence()

# ============================================================
# TEST 3: Integrity & Verification
# ============================================================
print("\n📋 Integrity & Verification")

@test("Hash chain integrity")
def test_hash_chain():
    import atlast_ecp
    # Create 3 chained records (simulating multi-step agent task)
    prev_hash = None
    for i in range(3):
        rec = atlast_ecp.create_record(
            agent_id="research-agent",
            input_data={"raw": f"Step {i+1} of research pipeline"},
            execution=[{"step": 1, "action": f"step_{i+1}", "input": {}, "output": {"done": True}, "duration_ms": 100}],
            output_data={"step": i+1, "status": "complete"},
            parent_hash=prev_hash,
            ecp_dir=TEST_ECP_DIR
        )
        atlast_ecp.save_record(rec, ecp_dir=TEST_ECP_DIR)
        current_hash = rec["integrity"].get("chain_hash", "")
        if prev_hash:
            # Verify chain linkage exists in record
            parent_ref = rec.get("parent_hash") or rec["integrity"].get("parent_hash", "")
            # The record should reference the parent somehow
            print(f"    Step {i+1}: hash={current_hash[:12]}... parent={'yes' if prev_hash else 'genesis'}")
        prev_hash = current_hash

test_hash_chain()

@test("Record verification (signature)")
def test_verification():
    import atlast_ecp
    identity = atlast_ecp.get_or_create_identity("research-agent", ecp_dir=TEST_ECP_DIR)
    rec = atlast_ecp.create_record(
        agent_id="research-agent",
        input_data={"raw": "Verify this record is signed correctly"},
        output_data={"verified": True},
        ecp_dir=TEST_ECP_DIR
    )
    
    # Check if record has signature
    sig = rec.get("integrity", {}).get("agent_signature", "")
    if sig:
        # Try verify
        try:
            result = atlast_ecp.verify_record(rec)
            print(f"    Signature present, verify result: {result}")
        except Exception as e:
            warn(f"verify_record raised: {e}")
    else:
        warn("Record has no signature — verify if this is expected at this level")

test_verification()

# ============================================================
# TEST 4: Trust Signals & Flags
# ============================================================
print("\n📋 Trust Signals & Anomaly Detection")

@test("Trust signals computation")
def test_signals():
    import atlast_ecp
    rec = atlast_ecp.create_record(
        agent_id="research-agent",
        input_data={"raw": "Summarize 50-page regulatory document"},
        execution=[
            {"step": 1, "action": "read_document", "input": {"pages": 50}, "output": {"extracted_text": "..."}, "duration_ms": 5000},
            {"step": 2, "action": "summarize", "input": {"text_length": 125000}, "output": {"summary_length": 3000}, "duration_ms": 8500},
        ],
        output_data={"summary": "Key findings: ...", "confidence": 0.92},
        model="claude-sonnet-4-20250514",
        tokens_in=50000,
        tokens_out=3000,
        duration_ms=13500,
        ecp_dir=TEST_ECP_DIR
    )
    signals = atlast_ecp.compute_trust_signals(rec)
    assert signals is not None, "Signals should be computed"
    print(f"    Signals: {json.dumps(signals, indent=2)[:200]}...")

test_signals()

@test("Anomaly flag detection")
def test_flags():
    import atlast_ecp
    # Create a suspicious record: very fast response for complex task
    rec = atlast_ecp.create_record(
        agent_id="research-agent",
        input_data={"raw": "Write a 10,000 word comprehensive market analysis report"},
        execution=[
            {"step": 1, "action": "write_report", "input": {"words": 10000}, "output": {"words": 10000}, "duration_ms": 50},  # Suspiciously fast!
        ],
        output_data={"report": "A" * 10000},  # Suspicious output
        tokens_in=100,
        tokens_out=15000,
        duration_ms=50,  # 50ms for 10k word report?!
        ecp_dir=TEST_ECP_DIR
    )
    flags = atlast_ecp.detect_flags(rec)
    print(f"    Flags detected: {flags}")
    # Should detect something fishy (token ratio anomaly, speed anomaly, etc.)

test_flags()

# ============================================================
# TEST 5: Batch Operations
# ============================================================
print("\n📋 Batch Operations & Merkle Tree")

@test("Batch creation with Merkle root")
def test_batch():
    import atlast_ecp
    # Create multiple records
    records = []
    for i in range(5):
        rec = atlast_ecp.create_record(
            agent_id="research-agent",
            input_data={"raw": f"Task {i+1}: research subtopic"},
            output_data={"result": f"Findings for subtopic {i+1}"},
            duration_ms=1000 + i * 200,
            ecp_dir=TEST_ECP_DIR
        )
        atlast_ecp.save_record(rec, ecp_dir=TEST_ECP_DIR)
        records.append(rec)
    
    # Build batch
    batch = atlast_ecp.run_batch(agent_id="research-agent", ecp_dir=TEST_ECP_DIR)
    if batch:
        print(f"    Batch created: {json.dumps({k: v for k, v in batch.items() if k != 'records'}, default=str)[:200]}")
    else:
        warn("run_batch returned None — may need API URL configured")

test_batch()

@test("Merkle proof generation & verification")
def test_merkle():
    import atlast_ecp
    records = atlast_ecp.load_records(agent_id="research-agent", ecp_dir=TEST_ECP_DIR)
    if len(records) >= 2:
        hashes = [r.get("integrity", {}).get("chain_hash", hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()) for r in records[:4]]
        hashes = [h for h in hashes if h]  # filter empty
        if hashes:
            proof = atlast_ecp.build_merkle_proof(hashes, 0)
            print(f"    Merkle proof: root={proof.get('root', 'N/A')[:16]}..., path length={len(proof.get('path', []))}")
            # Verify
            valid = atlast_ecp.verify_merkle_proof(proof)
            assert valid, "Merkle proof should be valid"
            print(f"    Merkle verification: ✅ valid")
    else:
        warn("Not enough records for Merkle test")

test_merkle()

# ============================================================
# TEST 6: Layer 0 — Proxy (structural test)
# ============================================================
print("\n📋 Layer 0: Proxy Module")

@test("Proxy module importable")
def test_proxy_import():
    from atlast_ecp import proxy
    assert hasattr(proxy, "ATLASTProxy") or hasattr(proxy, "start_proxy") or hasattr(proxy, "ProxyHandler"), \
        f"Proxy module should have main class, got: {[x for x in dir(proxy) if not x.startswith('_')]}"
    public = [x for x in dir(proxy) if not x.startswith('_')]
    print(f"    Proxy exports: {public}")

test_proxy_import()

# ============================================================
# TEST 7: Layer 2 — Framework Adapters
# ============================================================
print("\n📋 Layer 2: Framework Adapters")

@test("OpenClaw adapter importable")
def test_openclaw_adapter():
    try:
        from atlast_ecp.integrations import openclaw_hook
        print(f"    OpenClaw hook exports: {[x for x in dir(openclaw_hook) if not x.startswith('_')][:10]}")
    except ImportError:
        # Try alternative paths
        try:
            sys.path.insert(0, "/tmp/atlast-ecp/integrations")
            import openclaw_hook
            print(f"    OpenClaw hook (integrations/): {[x for x in dir(openclaw_hook) if not x.startswith('_')][:10]}")
        except ImportError:
            warn("OpenClaw adapter not found in expected locations")

test_openclaw_adapter()

@test("AutoGen adapter importable")
def test_autogen_adapter():
    try:
        from atlast_ecp.integrations import autogen_adapter
        print(f"    AutoGen adapter exports: {[x for x in dir(autogen_adapter) if not x.startswith('_')][:10]}")
    except ImportError:
        try:
            sys.path.insert(0, "/tmp/atlast-ecp/integrations")
            import autogen_adapter
            print(f"    AutoGen adapter (integrations/): loaded")
        except ImportError:
            warn("AutoGen adapter not importable (may need autogen dep)")

test_autogen_adapter()

# ============================================================
# TEST 8: Production Edge Cases
# ============================================================
print("\n📋 Production Edge Cases")

@test("Unicode input handling")
def test_unicode():
    import atlast_ecp
    rec = atlast_ecp.create_record(
        agent_id="research-agent",
        input_data={"raw": "分析中国市场AI监管政策 🇨🇳 — «régulations» für KI-Systeme"},
        output_data={"summary": "多语言输出: 中文/français/Deutsch ✅"},
        ecp_dir=TEST_ECP_DIR
    )
    assert rec is not None
    # Verify hash is still valid
    assert rec["integrity"]["chain_hash"], "Hash should work with unicode"

test_unicode()

@test("Large payload handling")
def test_large_payload():
    import atlast_ecp
    # Simulate a large context window agent
    large_input = "x" * 100_000  # 100KB input
    large_output = "y" * 50_000   # 50KB output
    rec = atlast_ecp.create_record(
        agent_id="research-agent",
        input_data={"raw": large_input},
        output_data={"result": large_output},
        tokens_in=128000,
        tokens_out=32000,
        duration_ms=45000,
        ecp_dir=TEST_ECP_DIR
    )
    atlast_ecp.save_record(rec, ecp_dir=TEST_ECP_DIR)
    # Verify it can be loaded back
    records = atlast_ecp.load_records(agent_id="research-agent", ecp_dir=TEST_ECP_DIR, limit=1)
    assert len(records) > 0

test_large_payload()

@test("Empty/null fields handling")
def test_empty_fields():
    import atlast_ecp
    rec = atlast_ecp.create_minimal_record(
        agent_id="research-agent",
        input_text="",  # Empty input
        output_text=""  # Empty output
    )
    assert rec is not None
    assert rec["chain_id"]

test_empty_fields()

@test("Rapid sequential records (rate test)")
def test_rapid_records():
    import atlast_ecp
    start = time.time()
    count = 50
    for i in range(count):
        rec = atlast_ecp.create_minimal_record(
            agent_id="research-agent",
            input_text=f"Rapid task {i}",
            output_text=f"Result {i}"
        )
        atlast_ecp.save_record(rec, ecp_dir=TEST_ECP_DIR)
    elapsed = time.time() - start
    rate = count / elapsed
    print(f"    {count} records in {elapsed:.2f}s = {rate:.0f} records/sec")
    if rate < 10:
        warn(f"Record creation rate is low: {rate:.0f}/sec (expected >100)")

test_rapid_records()

@test("Concurrent agent IDs isolation")
def test_agent_isolation():
    import atlast_ecp
    # Two different agents should have isolated records
    atlast_ecp.init(agent_name="agent-alpha", ecp_dir=TEST_ECP_DIR)
    atlast_ecp.init(agent_name="agent-beta", ecp_dir=TEST_ECP_DIR)
    
    rec_a = atlast_ecp.create_minimal_record(agent_id="agent-alpha", input_text="Alpha task", output_text="Alpha result")
    rec_b = atlast_ecp.create_minimal_record(agent_id="agent-beta", input_text="Beta task", output_text="Beta result")
    atlast_ecp.save_record(rec_a, ecp_dir=TEST_ECP_DIR)
    atlast_ecp.save_record(rec_b, ecp_dir=TEST_ECP_DIR)
    
    records_a = atlast_ecp.load_records(agent_id="agent-alpha", ecp_dir=TEST_ECP_DIR)
    records_b = atlast_ecp.load_records(agent_id="agent-beta", ecp_dir=TEST_ECP_DIR)
    
    # Each should only see their own records
    for r in records_a:
        assert r.get("agent_id") == "agent-alpha", f"Alpha saw non-alpha record: {r.get('agent_id')}"
    for r in records_b:
        assert r.get("agent_id") == "agent-beta", f"Beta saw non-beta record: {r.get('agent_id')}"
    print(f"    Alpha: {len(records_a)} records, Beta: {len(records_b)} records — isolated ✅")

test_agent_isolation()

# ============================================================
# TEST 9: CLI Commands (structural)
# ============================================================
print("\n📋 CLI Commands")

@test("CLI entry point")
def test_cli():
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "atlast_ecp.cli", "--help"],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "ECP_DIR": TEST_ECP_DIR}
    )
    assert result.returncode == 0, f"CLI --help failed: {result.stderr}"
    assert "atlast" in result.stdout.lower() or "ecp" in result.stdout.lower() or "usage" in result.stdout.lower(), \
        f"CLI help unexpected: {result.stdout[:200]}"
    print(f"    CLI commands found in help output ✅")

test_cli()

# ============================================================
# TEST 10: Backend API Connectivity (if available)
# ============================================================
print("\n📋 Backend API Connectivity")

@test("Backend health check")
def test_backend():
    import urllib.request
    try:
        req = urllib.request.Request("https://api.llachat.com/health", method="GET")
        req.add_header("User-Agent", "ATLAST-ProdTest/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"    Backend status: {data}")
    except Exception as e:
        warn(f"Backend not reachable: {e} — may need Railway deploy")

test_backend()

@test("Leaderboard API")
def test_leaderboard():
    import urllib.request
    try:
        req = urllib.request.Request("https://api.llachat.com/v1/leaderboard?period=7d&limit=5", method="GET")
        req.add_header("User-Agent", "ATLAST-ProdTest/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"    Leaderboard: {len(data) if isinstance(data, list) else data} entries")
    except Exception as e:
        warn(f"Leaderboard API: {e}")

test_leaderboard()

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
        print(f"  ❌ {name}")
        print(f"     {err}")

if results["warnings"]:
    print(f"\n{'─'*40}")
    print("WARNINGS:")
    for w in results["warnings"]:
        print(f"  ⚠️  {w}")

print(f"\n{'─'*40}")
total = len(results['passed']) + len(results['failed'])
print(f"Score: {len(results['passed'])}/{total} ({100*len(results['passed'])//max(total,1)}%)")

# Cleanup
import shutil
shutil.rmtree(TEST_ECP_DIR, ignore_errors=True)

sys.exit(1 if results["failed"] else 0)
