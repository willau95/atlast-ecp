"""
ATLAST ECP Server - EAS on Base Service

Modes:
  EAS_STUB_MODE=true  → deterministic stub UIDs (dev/testing)
  EAS_STUB_MODE=false → real EAS on Base via Alchemy/ethers

EAS on Base:
  - Contract: 0x4200000000000000000000000000000000000021 (Base mainnet)
  - Schema: registered once, ID stored in EAS_SCHEMA_UID env var
  - Cost: ~$0.001 per attestation on Base
"""

import hashlib
import time
from typing import Optional
from ..config import settings


# EAS contracts (same address on mainnet and Sepolia)
EAS_CONTRACT = "0x4200000000000000000000000000000000000021"

# Chain config: Base Sepolia (testnet, free) or Base mainnet
_USE_TESTNET = getattr(settings, 'EAS_CHAIN', 'sepolia') == 'sepolia'
BASE_CHAIN_ID = 84532 if _USE_TESTNET else 8453
BASE_RPC = "https://sepolia.base.org" if _USE_TESTNET else "https://mainnet.base.org"
EAS_SCAN_BASE = "https://base-sepolia.easscan.org" if _USE_TESTNET else "https://base.easscan.org"


async def write_attestation(
    merkle_root: str,
    agent_did: str,
    record_count: int,
    avg_latency_ms: int,
    batch_ts: int,
    ecp_version: str = "0.1",
) -> dict:
    """
    Write ECP batch attestation to EAS on Base.
    Returns dict with attestation_uid, eas_url, anchored_at.
    Falls back to stub mode if live mode fails or is not configured.
    """
    if settings.EAS_STUB_MODE == "true":
        return await _stub_attestation(merkle_root, agent_did, record_count, batch_ts)

    try:
        return await _live_attestation(
            merkle_root, agent_did, record_count,
            avg_latency_ms, batch_ts, ecp_version,
        )
    except Exception as e:
        # Fail-Open: fall back to stub if live fails
        import traceback
        print(f"EAS LIVE ERROR: {e}\n{traceback.format_exc()}")
        result = await _stub_attestation(merkle_root, agent_did, record_count, batch_ts)
        result["mode"] = "fallback_stub"
        result["error"] = str(e)
        return result


async def _stub_attestation(
    merkle_root: str,
    agent_did: str,
    record_count: int,
    batch_ts: int,
) -> dict:
    """Deterministic stub attestation for dev/testing."""
    payload = f"{merkle_root}:{agent_did}:{batch_ts}"
    uid_hex = hashlib.sha256(payload.encode()).hexdigest()
    attestation_uid = f"stub_{uid_hex[:16]}"

    return {
        "attestation_uid": attestation_uid,
        "eas_url": f"{EAS_SCAN_BASE}/attestation/view/{attestation_uid}",
        "anchored_at": int(time.time() * 1000),
        "mode": "stub",
    }


async def _live_attestation(
    merkle_root: str,
    agent_did: str,
    record_count: int,
    avg_latency_ms: int,
    batch_ts: int,
    ecp_version: str,
) -> dict:
    """
    Real EAS attestation on Base via web3.py.
    Requires: EAS_PRIVATE_KEY, EAS_SCHEMA_UID in env.
    Schema: "string agent_did,bytes32 merkle_root,uint64 record_count,uint64 batch_ts,string ecp_version"
    """
    from web3 import Web3
    from eth_abi import encode as abi_encode

    private_key = getattr(settings, 'EAS_PRIVATE_KEY', None)
    schema_uid = getattr(settings, 'EAS_SCHEMA_UID', None)

    if not private_key or not schema_uid:
        raise ValueError("EAS_PRIVATE_KEY and EAS_SCHEMA_UID required for live mode")

    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    account = w3.eth.account.from_key(private_key)

    EAS_ABI = [{
        "inputs": [{"components": [
            {"name": "schema", "type": "bytes32"},
            {"components": [
                {"name": "recipient", "type": "address"},
                {"name": "expirationTime", "type": "uint64"},
                {"name": "revocable", "type": "bool"},
                {"name": "refUID", "type": "bytes32"},
                {"name": "data", "type": "bytes"},
                {"name": "value", "type": "uint256"}
            ], "name": "data", "type": "tuple"}
        ], "name": "request", "type": "tuple"}],
        "name": "attest",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "payable",
        "type": "function"
    }]

    eas = w3.eth.contract(address=EAS_CONTRACT, abi=EAS_ABI)

    # Encode attestation data matching schema exactly
    merkle_bytes = bytes.fromhex(merkle_root.replace("sha256:", "")[:64])
    encoded_data = abi_encode(
        ['string', 'bytes32', 'uint64', 'uint64', 'string'],
        [agent_did, merkle_bytes, record_count, batch_ts, ecp_version]
    )

    # Build, sign, send transaction (sync web3 calls in async context)
    import asyncio
    loop = asyncio.get_event_loop()

    def _send_tx():
        tx = eas.functions.attest((
            bytes.fromhex(schema_uid[2:] if schema_uid.startswith("0x") else schema_uid),
            (
                "0x0000000000000000000000000000000000000000",  # recipient
                0,      # expirationTime
                False,  # revocable (matches on-chain schema)
                b'\x00' * 32,  # refUID
                encoded_data,   # data
                0,      # value
            ),
        )).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 500000,
            "gasPrice": w3.eth.gas_price,
            "chainId": BASE_CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        return tx_hash, receipt

    tx_hash, receipt = await loop.run_in_executor(None, _send_tx)
    tx_hash_hex = f"0x{tx_hash.hex()}"

    if receipt['status'] != 1:
        raise ValueError(f"Transaction reverted: {tx_hash_hex}")

    # Extract attestation UID from Attested event log data
    attestation_uid = tx_hash_hex
    if receipt.get('logs'):
        attestation_uid = f"0x{receipt['logs'][0]['data'].hex()}"

    return {
        "attestation_uid": attestation_uid,
        "tx_hash": tx_hash_hex,
        "eas_url": f"{EAS_SCAN_BASE}/attestation/view/{attestation_uid}",
        "anchored_at": int(time.time() * 1000),
        "mode": "live",
    }
