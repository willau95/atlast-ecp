"""
ECP Backend — EAS (Ethereum Attestation Service) on Base Integration
Phase 1 (MVP): Stub — stores locally, returns mock attestation_uid
Phase 2 (Week 9-10): Wire to real EAS on Base chain

The SDK calls our backend, our backend calls EAS.
Users never interact with the blockchain directly.
"""

import hashlib
import os
import time
from typing import Optional

# EAS mode: "stub" (default) or "live"
EAS_MODE = os.environ.get("EAS_MODE", "stub")

# Phase 2: Real EAS config
EAS_CHAIN = "base"
EAS_CONTRACT = "0x4200000000000000000000000000000000000021"  # EAS on Base
ECP_SCHEMA_UID = os.environ.get("ECP_SCHEMA_UID", "")        # Registered at launch
ATLAST_PRIVATE_KEY = os.environ.get("ATLAST_PRIVATE_KEY", "") # ATLAST multisig


async def write_attestation(
    merkle_root: str,
    agent_did: str,
    record_count: int,
    avg_latency_ms: int,
    batch_ts: int,
    ecp_version: str = "0.1",
) -> dict:
    """
    Write an EAS attestation for this batch.
    Returns: {attestation_uid, eas_url, anchored_at}
    """
    if EAS_MODE == "stub":
        return await _stub_attestation(merkle_root, agent_did, record_count, batch_ts)
    else:
        return await _live_attestation(merkle_root, agent_did, record_count, avg_latency_ms, batch_ts, ecp_version)


async def _stub_attestation(
    merkle_root: str,
    agent_did: str,
    record_count: int,
    batch_ts: int,
) -> dict:
    """
    Stub: generate deterministic fake attestation_uid for dev/testing.
    Replace with real EAS call in Week 9-10.
    """
    # Deterministic fake UID (so same batch always gets same UID in tests)
    payload = f"{merkle_root}:{agent_did}:{batch_ts}"
    uid_hex = hashlib.sha256(payload.encode()).hexdigest()
    attestation_uid = f"0x{uid_hex}"

    return {
        "attestation_uid": attestation_uid,
        "eas_url": f"https://base.easscan.org/attestation/view/{attestation_uid}",
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
    Phase 2: Real EAS attestation on Base.
    Requires: web3, eth_account packages + funded ATLAST wallet.

    TODO (Week 9-10):
    1. Register ECP Schema on EAS: atlast register-schema
    2. Fund ATLAST Safe multisig on Base
    3. Set ECP_SCHEMA_UID, ATLAST_PRIVATE_KEY env vars
    4. Uncomment and test this implementation
    """
    try:
        # from eth_account import Account
        # from web3 import Web3
        # from eas_sdk import EAS, SchemaEncoder

        # w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org"))
        # account = Account.from_key(ATLAST_PRIVATE_KEY)
        # eas = EAS(EAS_CONTRACT)
        # eas.connect(w3)

        # schema_encoder = SchemaEncoder(
        #     "bytes32 merkleRoot,string agentDid,uint256 recordCount,"
        #     "uint256 avgLatencyMs,uint256 batchTimestamp,string ecpVersion"
        # )
        # encoded_data = schema_encoder.encode_data([
        #     {"name": "merkleRoot", "value": bytes.fromhex(merkle_root[7:]), "type": "bytes32"},
        #     {"name": "agentDid", "value": agent_did, "type": "string"},
        #     {"name": "recordCount", "value": record_count, "type": "uint256"},
        #     {"name": "avgLatencyMs", "value": avg_latency_ms, "type": "uint256"},
        #     {"name": "batchTimestamp", "value": batch_ts, "type": "uint256"},
        #     {"name": "ecpVersion", "value": ecp_version, "type": "string"},
        # ])
        # tx = eas.attest({
        #     "schema": ECP_SCHEMA_UID,
        #     "data": {"recipient": "0x0000000000000000000000000000000000000000",
        #              "expirationTime": 0, "revocable": False,
        #              "data": encoded_data}
        # })
        # receipt = tx.wait()
        # attestation_uid = receipt.logs[0].topics[1].hex()
        # return {
        #     "attestation_uid": attestation_uid,
        #     "eas_url": f"https://base.easscan.org/attestation/view/{attestation_uid}",
        #     "anchored_at": int(time.time() * 1000),
        #     "mode": "live",
        # }
        raise NotImplementedError("Live EAS not yet configured. Set EAS_MODE=stub for development.")
    except NotImplementedError:
        raise
    except Exception as e:
        # Fail-Open: if EAS write fails, return stub result
        # The batch is already stored in our DB — it can be re-anchored later
        return await _stub_attestation(merkle_root, agent_did, record_count, batch_ts)
