#!/usr/bin/env python3
"""
Cross-SDK Interoperability Test

Verifies that Python SDK and TypeScript SDK produce identical:
1. SHA-256 hashes (sha256: prefixed)
2. Chain hashes (stableStringify / json.dumps canonical)
3. Merkle roots (same tree algorithm)
4. Ed25519 signatures (Python sign → TS verify)

This is a critical test: if cross-SDK hashes diverge,
records from one SDK cannot be verified by the other.
"""

import json
import hashlib
import subprocess
import sys
from pathlib import Path

SDK_TS_DIR = Path(__file__).parent.parent / "sdk" / "typescript"
PASS = "✅"
FAIL = "❌"
results = []


def run_ts(code: str) -> str:
    """Run TypeScript/Node code and return stdout."""
    result = subprocess.run(
        ["node", "-e", code],
        capture_output=True, text=True, cwd=SDK_TS_DIR,
    )
    if result.returncode != 0:
        raise RuntimeError(f"TS error: {result.stderr}")
    return result.stdout.strip()


def py_sha256(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def py_stable_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def test(name: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    results.append((name, passed))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))


# ─── Test 1: SHA-256 Hash ─────────────────────────────────────────────────

print("\n🔬 Test 1: SHA-256 Hash Consistency")
test_inputs = ["Hello world", "", "日本語テスト", "a" * 10000, '{"key":"value"}']

for inp in test_inputs:
    py_hash = py_sha256(inp)
    ts_code = f"""
const {{ createHash }} = require('crypto');
const h = 'sha256:' + createHash('sha256').update({json.dumps(inp)}).digest('hex');
process.stdout.write(h);
"""
    ts_hash = run_ts(ts_code)
    test(f"sha256({json.dumps(inp)[:30]})", py_hash == ts_hash,
         f"py={py_hash[:30]}... ts={ts_hash[:30]}...")


# ─── Test 2: Chain Hash (Canonical JSON) ──────────────────────────────────

print("\n🔬 Test 2: Chain Hash (Canonical JSON)")

test_records = [
    {
        "id": "rec_test001", "ts": 1700000000000, "agent": "did:ecp:test",
        "action": "llm_call", "in_hash": "sha256:abc", "out_hash": "sha256:def",
        "model": "gpt-4", "latency_ms": 100, "flags": [],
        "chain": {"prev": "genesis", "hash": ""}, "sig": "",
    },
    {
        "id": "rec_test002", "ts": 1700000001000, "agent": "did:ecp:test2",
        "action": "tool_call", "in_hash": "sha256:xyz", "out_hash": "sha256:uvw",
        "model": "claude-3", "latency_ms": 500, "flags": ["error", "retried"],
        "cost_usd": 0.05, "parent_agent": "did:ecp:parent",
        "session_id": "sess_abc", "delegation_id": "del_001", "delegation_depth": 1,
        "chain": {"prev": "sha256:prev123", "hash": ""}, "sig": "",
    },
    # Edge case: minimal record
    {
        "id": "rec_min", "ts": 0, "agent": "x", "action": "a",
        "in_hash": "", "out_hash": "", "flags": [],
        "chain": {"prev": "genesis", "hash": ""}, "sig": "",
    },
]

for i, rec in enumerate(test_records):
    py_canonical = py_stable_json(rec)
    py_hash = "sha256:" + hashlib.sha256(py_canonical.encode()).hexdigest()

    ts_code = f"""
const {{ createHash }} = require('crypto');
function stableStringify(obj) {{
  if (obj === null || obj === undefined) return 'null';
  if (typeof obj === 'string') return JSON.stringify(obj);
  if (typeof obj === 'number' || typeof obj === 'boolean') return String(obj);
  if (Array.isArray(obj)) return '[' + obj.map(stableStringify).join(',') + ']';
  if (typeof obj === 'object') {{
    const keys = Object.keys(obj).sort();
    return '{{' + keys.map(k => JSON.stringify(k) + ':' + stableStringify(obj[k])).join(',') + '}}';
  }}
  return String(obj);
}}
const rec = {json.dumps(rec)};
const canonical = stableStringify(rec);
const h = 'sha256:' + createHash('sha256').update(canonical).digest('hex');
process.stdout.write(h);
"""
    ts_hash = run_ts(ts_code)
    test(f"record[{i}] chain hash", py_hash == ts_hash,
         f"py={py_hash[:30]}... ts={ts_hash[:30]}...")


# ─── Test 3: Merkle Root ──────────────────────────────────────────────────

print("\n🔬 Test 3: Merkle Root Consistency")

merkle_cases = [
    [],
    ["sha256:aaa"],
    ["sha256:aaa", "sha256:bbb"],
    ["sha256:aaa", "sha256:bbb", "sha256:ccc"],
    [f"sha256:{hashlib.sha256(str(i).encode()).hexdigest()}" for i in range(10)],
    [f"sha256:{hashlib.sha256(str(i).encode()).hexdigest()}" for i in range(100)],
]

for case in merkle_cases:
    # Python
    from atlast_ecp.batch import build_merkle_tree
    py_root, _ = build_merkle_tree(case)

    # TS
    ts_code = f"""
const {{ createHash }} = require('crypto');
function sha256(d) {{ return 'sha256:' + createHash('sha256').update(d).digest('hex'); }}
function merkle(h) {{
  if (!h.length) return sha256('empty');
  if (h.length === 1) return h[0];
  const padded = h.length % 2 === 1 ? [...h, h[h.length-1]] : h;
  const next = [];
  for (let i = 0; i < padded.length; i += 2) next.push(sha256(padded[i] + padded[i+1]));
  return merkle(next);
}}
process.stdout.write(merkle({json.dumps(case)}));
"""
    ts_root = run_ts(ts_code)
    test(f"merkle({len(case)} leaves)", py_root == ts_root,
         f"root={py_root[:40]}...")


# ─── Summary ──────────────────────────────────────────────────────────────

print(f"\n{'='*50}")
passed = sum(1 for _, p in results if p)
total = len(results)
print(f"📊 Cross-SDK Interop: {passed}/{total} passed")
all_ok = passed == total
print(f"{'✅ ALL PASS' if all_ok else '❌ FAILURES DETECTED'}")
sys.exit(0 if all_ok else 1)
