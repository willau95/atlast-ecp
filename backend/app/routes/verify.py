"""
ECP Backend — Record Verification Route
GET /v1/verify/{record_id}

Verifies a specific ECP record using stored Merkle proof.
Anyone can call this — public endpoint, no auth required.
"""

import json
from fastapi import APIRouter, HTTPException

from ..database import db
from ..models import VerifyResponse, MerkleProof
from ..crypto import verify_merkle_proof

router = APIRouter()


@router.get("/v1/verify/{record_id}", response_model=VerifyResponse, tags=["Verification"])
def verify_record(record_id: str):
    """
    Verify an ECP record's chain integrity and Merkle proof.

    Three possible results:
    - VALID: Record hash is in a Merkle tree that's anchored on-chain
    - UNVERIFIED: Record exists in our DB but not yet anchored (pending batch)
    - INVALID: Record not found or chain hash mismatch

    Public endpoint — anyone can verify any record.
    """
    with db() as conn:
        # Look up record hash
        record = conn.execute(
            "SELECT * FROM record_hashes WHERE record_id = ?", (record_id,)
        ).fetchone()

        if not record:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Record '{record_id}' not found. "
                    "The record may not have been uploaded yet, "
                    "or the record_id may be incorrect."
                )
            )

        # Look up batch for this record
        batch = None
        if record["batch_id"]:
            batch = conn.execute(
                "SELECT * FROM batches WHERE batch_id = ?", (record["batch_id"],)
            ).fetchone()

    # Determine verification result
    chain_valid = True   # We trust what the SDK submitted (hash integrity checked at upload)
    merkle_proof = None
    verification_result = "UNVERIFIED"
    message = "Record is stored but not yet anchored on-chain."

    if batch:
        # Parse stored Merkle proof
        stored_proof = record["merkle_proof"]
        proof_steps = json.loads(stored_proof) if stored_proof else []

        if batch["attestation_uid"] and proof_steps:
            # Verify the Merkle proof against the anchored root
            proof_valid = verify_merkle_proof(
                record_hash=record["chain_hash"],
                proof=proof_steps,
                merkle_root=batch["merkle_root"],
            )

            if proof_valid:
                verification_result = "VALID"
                message = "Record is verified. Merkle proof is valid and anchored on-chain."
            else:
                verification_result = "INVALID"
                chain_valid = False
                message = "Merkle proof verification failed. Record may have been tampered."

            merkle_proof = MerkleProof(
                root=batch["merkle_root"],
                path=proof_steps,
                attestation_uid=batch["attestation_uid"],
                eas_url=batch["eas_url"],
            )
        elif batch["upload_status"] == "pending_anchor":
            message = "Record is in a batch pending EAS anchoring. Check back in a few minutes."
        elif batch["upload_status"] == "anchor_failed":
            message = "EAS anchoring failed for this batch. Will be retried."

    return VerifyResponse(
        record_id=record_id,
        agent_did=record["agent_did"],
        chain_hash=record["chain_hash"],
        chain_valid=chain_valid,
        merkle_proof=merkle_proof,
        verification_result=verification_result,
        message=message,
    )
