#!/usr/bin/env python3
"""ATLAST ECP Stress Test — 100 records, batch upload, verify integrity"""
import sys, time, json, requests, concurrent.futures
sys.path.insert(0, "/tmp/atlast-ecp/sdk")

API = "https://api.llachat.com/v1"

print("=" * 60)
print("  ATLAST ECP STRESS TEST")
print("=" * 60)

# Clean state
import shutil, os
shutil.rmtree(os.path.expanduser("~/.ecp"), ignore_errors=True)

from atlast_ecp.identity import get_or_create_identity
from atlast_ecp.core import record
from atlast_ecp.batch import run_batch, _load_batch_state
from atlast_ecp.storage import load_records
from atlast_ecp.record import compute_chain_hash

identity = get_or_create_identity()
did = identity["did"]
print(f"\nAgent: {did}")

# Register
requests.post(f"{API}/agent/register", json={
    "did": did, "name": "stress-test-agent", "pub_key": identity["pub_key"],
    "frameworks": ["atlast-sdk"], "sdk_version": "0.4.0"
})

# --- Test 1: Rapid-fire 100 records ---
print(f"\n[Test 1] Creating 100 records rapidly...")
t0 = time.time()
ids = []
for i in range(100):
    rid = record(
        input_content=f"Stress test prompt {i}: Analyze data batch {i} with parameters alpha={i*0.1:.1f}",
        output_content=f"Analysis complete for batch {i}. Key findings: metric_a={i*2.5:.1f}, metric_b={i*0.7:.2f}, status=nominal",
        model=["gpt-4o", "claude-sonnet-4-20250514", "gemini-pro", "qwen-72b"][i % 4],
        tokens_in=50 + i * 3,
        tokens_out=80 + i * 5,
        latency_ms=100 + (i % 20) * 50,
    )
    ids.append(rid)
elapsed = time.time() - t0
print(f"  ✅ 100 records in {elapsed:.2f}s ({100/elapsed:.0f} records/sec)")

# --- Test 2: Chain integrity ---
print(f"\n[Test 2] Verifying chain integrity for all 100 records...")
all_records = load_records(limit=200)
ok = 0
for rec in all_records:
    expected = compute_chain_hash(rec)
    actual = rec.get("chain", {}).get("hash", "")
    if expected == actual:
        ok += 1
print(f"  ✅ {ok}/{len(all_records)} records have valid chain hashes")

# Check parent chain links
linked = sum(1 for r in all_records if r.get("chain", {}).get("parent"))
print(f"  ✅ {linked}/{len(all_records)} records linked to parent (first record has no parent)")

# --- Test 3: Batch upload ---
print(f"\n[Test 3] Batch upload (100 records + EAS on-chain)...")
t0 = time.time()
run_batch()
elapsed = time.time() - t0
state = _load_batch_state()
att = state.get("last_attestation_uid", "")
print(f"  ✅ Batch uploaded in {elapsed:.1f}s")
print(f"  Merkle root: {state.get('last_merkle_root', '')[:60]}")
print(f"  Attestation: {att[:66]}")
is_live = att.startswith("0x") and not att.startswith("stub_")
print(f"  Mode: {'🔗 ON-CHAIN' if is_live else '⚠️ STUB'}")

# --- Test 4: Trust Score ---
print(f"\n[Test 4] Trust Score after 100 records...")
r = requests.get(f"{API}/trust-score/{did}")
ts = r.json()
print(f"  Score: {ts.get('trust_score', '?')}/1000")
print(f"  Breakdown: {json.dumps(ts.get('breakdown', {}))}")

# --- Test 5: Concurrent record creation ---
print(f"\n[Test 5] Concurrent record creation (50 threads × 2 records)...")
t0 = time.time()
results = []
def create_record(idx):
    return record(
        input_content=f"Concurrent test {idx}",
        output_content=f"Response {idx}",
        model="gpt-4o-mini",
        tokens_in=20, tokens_out=30, latency_ms=50,
    )

with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    futures = [executor.submit(create_record, i) for i in range(100)]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

valid = sum(1 for r in results if r and r.startswith("rec_"))
elapsed = time.time() - t0
print(f"  ✅ {valid}/100 concurrent records in {elapsed:.2f}s ({100/elapsed:.0f} records/sec)")

# --- Test 6: Second batch ---
print(f"\n[Test 6] Second batch upload...")
t0 = time.time()
run_batch()
elapsed = time.time() - t0
state2 = _load_batch_state()
print(f"  ✅ Batch #{state2.get('total_batches', '?')} in {elapsed:.1f}s")
att2 = state2.get("last_attestation_uid", "")
print(f"  Attestation: {att2[:66]}")

# --- Summary ---
total_records = load_records(limit=500)
print(f"\n{'=' * 60}")
print(f"  STRESS TEST COMPLETE")
print(f"{'=' * 60}")
print(f"  Total records: {len(total_records)}")
print(f"  Batches: {state2.get('total_batches', '?')}")
print(f"  EAS mode: {'ON-CHAIN 🔗' if is_live else 'STUB'}")
print(f"  Trust score: {ts.get('trust_score', '?')}/1000")
print(f"  All chain hashes valid: {'✅' if ok == 100 else '❌'}")
