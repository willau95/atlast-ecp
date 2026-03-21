"""
E2E Full Chain Test — ATLAST ECP Server
Tests the complete flow: SDK upload → pending batch → anchor → webhook → verify

Usage:
    python tests/test_e2e_full_chain.py

Requires:
    - ATLAST ECP Server running (ecp-server-production.up.railway.app)
    - LLaChat backend running (api.llachat.com)
    - Valid agent credentials in ~/.ecp/production-agents/atlas.json
"""

import hashlib
import json
import os
import sys
import time
import httpx

# ── Config ──────────────────────────────────────────────────────────────────

ECP_SERVER = os.getenv("ECP_SERVER", "https://ecp-server-production.up.railway.app")
LLACHAT_API = os.getenv("LLACHAT_API", "https://api.llachat.com")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "4b141c3e46e735a409bf95e010b46335724285c81c5e4e6319af2e252176bf4a")
AGENT_KEY_FILE = os.path.expanduser("~/.ecp/production-agents/atlas.json")

passed = 0
failed = 0
skipped = 0


def test(name):
    def decorator(func):
        def wrapper():
            global passed, failed, skipped
            try:
                result = func()
                if result == "SKIP":
                    print(f"  ⏭️  {name} — SKIPPED")
                    skipped += 1
                else:
                    print(f"  ✅ {name}")
                    passed += 1
                return result
            except Exception as e:
                print(f"  ❌ {name} — {e}")
                failed += 1
                return None
        return wrapper
    return decorator


# ── F1: ECP Server Health ───────────────────────────────────────────────────

@test("F1.1 ECP Server health")
def test_ecp_health():
    r = httpx.get(f"{ECP_SERVER}/health", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "ecp-server"
    return data

@test("F1.2 ECP Server discovery")
def test_discovery():
    r = httpx.get(f"{ECP_SERVER}/.well-known/ecp.json", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["ecp_version"] == "1.0"
    assert "eas_anchoring" in data["capabilities"]
    return data

@test("F1.3 ECP Server stats")
def test_stats():
    r = httpx.get(f"{ECP_SERVER}/v1/stats", timeout=10)
    assert r.status_code == 200
    return r.json()

@test("F1.4 Security headers present")
def test_security_headers():
    r = httpx.get(f"{ECP_SERVER}/health", timeout=10)
    assert "x-content-type-options" in r.headers
    assert "x-frame-options" in r.headers
    assert "strict-transport-security" in r.headers
    assert "x-request-id" in r.headers
    return True


# ── F2: LLaChat Integration ────────────────────────────────────────────────

@test("F2.1 LLaChat health")
def test_llachat_health():
    r = httpx.get(f"{LLACHAT_API}/v1/health", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    return data

@test("F2.2 Pending batches endpoint (via internal token)")
def test_pending_batches():
    r = httpx.get(
        f"{LLACHAT_API}/v1/internal/pending-batches",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert "batches" in data
    return data

@test("F2.3 Pending batches rejects bad token")
def test_pending_batches_bad_token():
    r = httpx.get(
        f"{LLACHAT_API}/v1/internal/pending-batches",
        headers={"X-Internal-Token": "wrong-token"},
        timeout=10,
    )
    assert r.status_code == 401
    return True

@test("F2.4 Batch-anchored rejects nonexistent batch")
def test_batch_anchored_404():
    r = httpx.post(
        f"{LLACHAT_API}/v1/internal/batch-anchored",
        headers={"X-Internal-Token": INTERNAL_TOKEN, "Content-Type": "application/json"},
        json={"batch_id": "nonexistent-test-id", "attestation_uid": "0xtest"},
        timeout=10,
    )
    assert r.status_code == 404
    return True


# ── F3: Anchor Flow ────────────────────────────────────────────────────────

@test("F3.1 Anchor-now endpoint (requires internal token)")
def test_anchor_now():
    r = httpx.post(
        f"{ECP_SERVER}/v1/internal/anchor-now",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "processed" in data
    return data

@test("F3.2 Anchor-now rejects no token")
def test_anchor_now_no_token():
    r = httpx.post(f"{ECP_SERVER}/v1/internal/anchor-now", timeout=10)
    assert r.status_code in (401, 422)
    return True

@test("F3.3 Cron status")
def test_cron_status():
    r = httpx.get(
        f"{ECP_SERVER}/v1/internal/cron-status",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("healthy", "degraded")
    assert "interval_minutes" in data
    return data


# ── F4: Verification ───────────────────────────────────────────────────────

@test("F4.1 Merkle verify — valid tree (SDK-compatible)")
def test_merkle_valid():
    # Use sha256: prefix to match SDK convention
    def sha256_prefixed(data: str) -> str:
        return "sha256:" + hashlib.sha256(data.encode()).hexdigest()

    h1 = sha256_prefixed("record1")
    h2 = sha256_prefixed("record2")
    # Root = sha256:(h1 + h2) — no sorting, order-preserving like SDK
    root = sha256_prefixed(h1 + h2)

    r = httpx.post(
        f"{ECP_SERVER}/v1/verify/merkle",
        json={"merkle_root": root, "record_hashes": [h1, h2]},
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True, f"Expected valid but got {data}"
    return data

@test("F4.2 Merkle verify — invalid root")
def test_merkle_invalid():
    r = httpx.post(
        f"{ECP_SERVER}/v1/verify/merkle",
        json={"merkle_root": "wrong", "record_hashes": ["abc", "def"]},
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False
    return data

@test("F4.3 Attestation lookup")
def test_attestation_lookup():
    r = httpx.get(f"{ECP_SERVER}/v1/verify/0xtest_uid_12345", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["chain"] == "sepolia"
    assert "explorer_url" in data
    return data

@test("F4.4 Attestations list")
def test_attestations_list():
    r = httpx.get(f"{ECP_SERVER}/v1/attestations", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "attestations" in data
    return data


# ── F5: Webhook Token ──────────────────────────────────────────────────────

@test("F5.1 Old webhook token rejected")
def test_old_webhook_token():
    r = httpx.post(
        f"{LLACHAT_API}/v1/internal/ecp-webhook",
        headers={"X-ECP-Webhook-Token": "ecp-internal-2026", "Content-Type": "application/json"},
        json={"cert_id": "test", "agent_did": "test"},
        timeout=10,
    )
    assert r.status_code == 401
    return True


# ── Run All ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔬 ATLAST ECP Server — E2E Full Chain Test\n")
    print(f"  ECP Server: {ECP_SERVER}")
    print(f"  LLaChat:    {LLACHAT_API}")
    print()

    tests = [
        test_ecp_health, test_discovery, test_stats, test_security_headers,
        test_llachat_health, test_pending_batches, test_pending_batches_bad_token,
        test_batch_anchored_404,
        test_anchor_now, test_anchor_now_no_token, test_cron_status,
        test_merkle_valid, test_merkle_invalid, test_attestation_lookup,
        test_attestations_list,
        test_old_webhook_token,
    ]

    for t in tests:
        t()

    print(f"\n{'='*50}")
    print(f"  ✅ Passed: {passed}  ❌ Failed: {failed}  ⏭️  Skipped: {skipped}")
    print(f"{'='*50}\n")

    sys.exit(1 if failed > 0 else 0)
