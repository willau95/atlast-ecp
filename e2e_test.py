#!/usr/bin/env python3
"""
ATLAST ECP — Full End-to-End Closure Test
SDK → Backend → EAS On-Chain → Trust Score → Certificate → Leaderboard
"""
import sys, os, json, time, requests

sys.path.insert(0, "/tmp/atlast-ecp/sdk")

API = "https://api.llachat.com/v1"

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

def check(label, ok, detail=""):
    status = "✅" if ok else "❌"
    print(f"  {status} {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        print(f"     FAILED!")
    return ok

# ─── Step 0: Health Check ───
section("Step 0: Backend Health")
r = requests.get(f"{API}/health", timeout=10)
health = r.json()
check("Backend reachable", r.status_code == 200)
check("Database OK", health.get("database") == "ok")
check("Redis OK", health.get("redis") == "ok")
check("Worker OK", health.get("worker") == "ok")
check("EAS mode", health.get("eas_mode") == "live", health.get("eas_mode"))

# ─── Step 1: Identity ───
section("Step 1: SDK Identity")
from atlast_ecp.identity import get_or_create_identity
identity = get_or_create_identity()
did = identity["did"]
check("Identity created", did.startswith("did:ecp:"), did)

# ─── Step 2: Agent Registration ───
section("Step 2: Agent Registration")
reg_payload = {
    "did": did,
    "name": "e2e-test-agent",
    "pub_key": identity["pub_key"],
    "description": "ATLAST E2E closure test agent",
    "frameworks": ["atlast-sdk"],
    "sdk_version": "0.4.0"
}
r = requests.post(f"{API}/agent/register", json=reg_payload, timeout=10)
check("Agent registered", r.status_code in (200, 201, 409), f"status={r.status_code}")
if r.status_code == 409:
    print("    (already registered — OK)")

# ─── Step 3: Create ECP Records ───
section("Step 3: Create ECP Records")
from atlast_ecp.core import record
record_ids = []
for i in range(5):
    rid = record(
        input_content=f"E2E test prompt #{i+1}: What is {i+1}+{i+1}?",
        output_content=f"The answer is {(i+1)*2}.",
        model="gpt-4o-mini",
        tokens_in=25 + i*5,
        tokens_out=10 + i*3,
        latency_ms=150 + i*50,
    )
    record_ids.append(rid)
    check(f"Record #{i+1}", rid.startswith("rec_"), rid[:40])

# ─── Step 4: Batch Upload (using run_batch) ───
section("Step 4: Batch Upload via run_batch()")
from atlast_ecp.batch import run_batch, _load_batch_state

# Reset batch state so it picks up our records
state_before = _load_batch_state()
print(f"  State before: total_batches={state_before.get('total_batches', 0)}")

run_batch()

state_after = _load_batch_state()
total_after = state_after.get("total_batches", 0)
merkle = state_after.get("last_merkle_root", "")
attestation = state_after.get("last_attestation_uid", "")

check("Batch uploaded", total_after > state_before.get("total_batches", 0),
      f"total_batches: {state_before.get('total_batches',0)} → {total_after}")
check("Merkle root", merkle.startswith("sha256:"), merkle[:50])
check("Attestation UID", bool(attestation), attestation[:50] if attestation else "NONE")

# ─── Step 5: Trust Score ───
section("Step 5: Trust Score")
time.sleep(1)  # Allow backend to process
r = requests.get(f"{API}/trust-score/{did}", timeout=10)
if r.status_code == 200:
    ts = r.json()
    score = ts.get("score", ts.get("trust_score", 0))
    check("Trust score retrieved", score > 0, f"score={score}")
    print(f"    Full response: {json.dumps(ts, indent=2)[:500]}")
else:
    check("Trust score retrieved", False, f"status={r.status_code} body={r.text[:200]}")

# ─── Step 6: Certificate ───
section("Step 6: Certificate")
cert_payload = {"agent_did": did, "task_name": "E2E Closure Test"}
r = requests.post(f"{API}/certificate/create", json=cert_payload, timeout=10)
if r.status_code in (200, 201):
    cert = r.json()
    check("Certificate created", True, f"cert_id={cert.get('certificate_id', cert.get('id', 'unknown'))}")
    print(f"    Full response: {json.dumps(cert, indent=2)[:500]}")
else:
    check("Certificate created", False, f"status={r.status_code} body={r.text[:300]}")

# ─── Step 7: Leaderboard ───
section("Step 7: Leaderboard")
r = requests.get(f"{API}/leaderboard", params={"type": "trust", "limit": 50}, timeout=10)
if r.status_code == 200:
    lb = r.json()
    entries = lb.get("items", lb if isinstance(lb, list) else [])
    total = lb.get("total", len(entries))
    check("Leaderboard retrieved", len(entries) > 0, f"{len(entries)} agents (total: {total})")
    # Check if our agent is on the board (by handle or trust score)
    our_entry = [e for e in entries if "e2e-test-agent" in e.get("handle", "")]
    check("Our agent on leaderboard", len(our_entry) > 0,
          f"rank={our_entry[0].get('rank', '?')}, score={our_entry[0].get('trust_score', '?')}" if our_entry else "NOT FOUND")
else:
    check("Leaderboard retrieved", False, f"status={r.status_code}")

# ─── Step 8: EAS On-Chain Verification ───
section("Step 8: EAS On-Chain Verification")
if attestation and attestation.startswith("0x"):
    check("EAS attestation UID", True, attestation)
    # Verify on Base Sepolia explorer
    explorer_url = f"https://base-sepolia.easscan.org/attestation/view/{attestation}"
    print(f"    🔗 Verify on-chain: {explorer_url}")
    # Try to fetch from EAS API
    try:
        eas_r = requests.get(f"https://base-sepolia.easscan.org/graphql", 
            json={"query": f'{{ attestation(where: {{ id: "{attestation}" }}) {{ id attester time }} }}'},
            timeout=10)
        if eas_r.status_code == 200:
            eas_data = eas_r.json()
            att = eas_data.get("data", {}).get("attestation", {})
            check("On-chain attestation verified", bool(att), 
                  f"attester={att.get('attester','?')}, time={att.get('time','?')}")
    except Exception as e:
        print(f"    ⚠️  Could not query EAS GraphQL: {e}")
elif attestation:
    check("EAS attestation (stub mode)", True, attestation)
else:
    check("EAS attestation UID", False, "No attestation returned")

# ─── Step 9: Chain Integrity ───
section("Step 9: Local Chain Integrity")
from atlast_ecp.storage import load_records
from atlast_ecp.record import compute_chain_hash
all_records = load_records(limit=100)
integrity_ok = True
for rec in all_records[-5:]:  # Check our 5 records
    expected = compute_chain_hash(rec)
    actual = rec.get("chain", {}).get("hash", "")
    if expected != actual:
        integrity_ok = False
        print(f"    ❌ Hash mismatch for {rec.get('id','?')}")
check("Chain hash integrity", integrity_ok, f"checked {min(5, len(all_records))} records")

# ─── Summary ───
section("E2E CLOSURE TEST COMPLETE")
print(f"""
  Agent DID:      {did}
  Records:        {len(record_ids)}
  Merkle Root:    {merkle[:60]}
  Attestation:    {attestation[:60] if attestation else 'N/A'}
  Backend:        {API}
""")
