#!/usr/bin/env python3
"""ST3: 24-hour stability test — 1 record every 5 minutes, checks memory + chain integrity."""

import os, sys, time, json, traceback, psutil, gc
from datetime import datetime, timezone

# Force test environment
os.environ.setdefault("ECP_DIR", "/tmp/test_st3_stability")
os.environ.setdefault("ECP_API_URL", "https://api.weba0.com/v1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "python"))

from atlast_ecp.core import record, record_minimal
from atlast_ecp.storage import load_records, count_records
from atlast_ecp.record import compute_chain_hash, record_to_dict
from atlast_ecp.identity import get_or_create_identity

def verify_chain(records):
    """Verify chain hash integrity across all records."""
    if not records:
        return True
    for i, rec in enumerate(records):
        d = rec if isinstance(rec, dict) else record_to_dict(rec)
        expected = compute_chain_hash(d)
        if d.get("chain_hash") and d["chain_hash"] != expected:
            return False
    return True

INTERVAL_SEC = 300  # 5 minutes
TOTAL_DURATION_SEC = 86400  # 24 hours
LOG_FILE = "/tmp/test_st3_stability/st3_log.jsonl"

def get_memory_mb():
    proc = psutil.Process(os.getpid())
    return proc.memory_info().rss / (1024 * 1024)

def main():
    os.makedirs("/tmp/test_st3_stability", exist_ok=True)
    identity = get_or_create_identity()
    print(f"ST3 started at {datetime.now(timezone.utc).isoformat()}")
    print(f"DID: {identity['did']}")
    print(f"Interval: {INTERVAL_SEC}s | Duration: {TOTAL_DURATION_SEC}s | Log: {LOG_FILE}")

    start = time.time()
    iteration = 0
    errors = 0
    mem_baseline = get_memory_mb()

    while time.time() - start < TOTAL_DURATION_SEC:
        iteration += 1
        ts = datetime.now(timezone.utc).isoformat()
        mem_now = get_memory_mb()
        mem_delta = mem_now - mem_baseline

        try:
            # Alternate between record() and record_minimal()
            if iteration % 2 == 1:
                rec = record(
                    input_content=f"ST3 stability test iteration {iteration} at {ts}",
                    output_content=f"Response for iteration {iteration}: system healthy, mem={mem_now:.1f}MB",
                    step_type="stability_check",
                    session_id=f"st3_session_{start:.0f}",
                )
            else:
                rec = record_minimal(
                    input_content=f"ST3 minimal iteration {iteration} at {ts}",
                    output_content=f"Minimal response {iteration}: delta_mem={mem_delta:.1f}MB",
                    agent="st3-stability-agent",
                    action="minimal_check",
                )

            # Verify chain every 10 iterations
            chain_ok = None
            if iteration % 10 == 0:
                all_records = load_records()
                chain_ok = verify_chain(all_records)
                gc.collect()

            total_records = count_records()
            entry = {
                "iteration": iteration,
                "timestamp": ts,
                "record_id": rec,  # record() returns record_id string
                "method": "record" if iteration % 2 == 1 else "record_minimal",
                "mem_mb": round(mem_now, 1),
                "mem_delta_mb": round(mem_delta, 1),
                "chain_verified": chain_ok,
                "total_records": total_records,
                "status": "OK",
            }
        except Exception as e:
            errors += 1
            entry = {
                "iteration": iteration,
                "timestamp": ts,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "mem_mb": round(mem_now, 1),
                "status": "ERROR",
            }

        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")

        elapsed = time.time() - start
        print(f"[{iteration}] {entry['status']} | mem={mem_now:.1f}MB(Δ{mem_delta:+.1f}) | records={entry.get('total_records','?')} | elapsed={elapsed/3600:.1f}h | errors={errors}")

        time.sleep(INTERVAL_SEC)

    # Final summary
    total_records = count_records()
    records = load_records()
    chain_ok = verify_chain(records)
    mem_final = get_memory_mb()

    summary = {
        "test": "ST3_24h_stability",
        "iterations": iteration,
        "errors": errors,
        "total_records": total_records,
        "chain_integrity": chain_ok,
        "mem_baseline_mb": round(mem_baseline, 1),
        "mem_final_mb": round(mem_final, 1),
        "mem_leak_mb": round(mem_final - mem_baseline, 1),
        "duration_hours": round((time.time() - start) / 3600, 2),
        "verdict": "PASS" if errors == 0 and chain_ok else "FAIL",
    }

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps({"SUMMARY": summary}) + "\n")

    print(f"\n{'='*60}")
    print(f"ST3 FINAL: {summary['verdict']}")
    print(json.dumps(summary, indent=2))

    with open("/tmp/test_st3_stability/RESULT.json", "w") as f:
        json.dumps(summary, f, indent=2)

if __name__ == "__main__":
    main()
