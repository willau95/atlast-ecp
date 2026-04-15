"""
Anchor Coordinator — ensures safe, non-concurrent EAS anchoring.

Responsibilities:
  1. Process-level asyncio.Lock — prevents concurrent anchor within one instance
  2. DB-level distributed lock — prevents concurrent anchor across Railway instances
  3. Nonce tracking — reliable nonce management for EAS transactions
  4. Gas balance checks — pause anchoring when wallet is too low
"""

import asyncio
import uuid
import structlog
from datetime import datetime, timezone, timedelta

from ..config import settings
from ..db.database import get_session

logger = structlog.get_logger()

# ── Process-level lock ──────────────────────────────────────────────────────

_anchor_lock = asyncio.Lock()

# ── Constants ───────────────────────────────────────────────────────────────

MAX_RETRY_COUNT = 4
MIN_GAS_BALANCE_WEI = 500_000_000_000_000  # 0.0005 ETH
LOCK_TTL_SECONDS = 300  # 5 minutes
_INSTANCE_ID = f"inst_{uuid.uuid4().hex[:12]}"


async def try_acquire_lock() -> bool:
    """
    Acquire process + DB distributed lock for anchoring.
    Returns True if lock acquired, False if another anchor is running.
    """
    if _anchor_lock.locked():
        logger.info("anchor_skip_process_locked")
        return False

    # Try DB-level lock
    try:
        session = await get_session()
        if session is not None:
            from sqlalchemy import text
            async with session:
                # Try to acquire: only succeeds if no lock or lock expired
                result = await session.execute(text("""
                    INSERT INTO anchor_lock (id, instance_id, acquired_at, ttl_seconds)
                    VALUES ('singleton', :inst, NOW(), :ttl)
                    ON CONFLICT (id) DO UPDATE
                    SET instance_id = :inst, acquired_at = NOW()
                    WHERE anchor_lock.acquired_at + make_interval(secs => anchor_lock.ttl_seconds) < NOW()
                    RETURNING id
                """), {"inst": _INSTANCE_ID, "ttl": LOCK_TTL_SECONDS})
                row = result.fetchone()
                if row is None:
                    logger.info("anchor_skip_db_locked")
                    return False
                await session.commit()
    except Exception as e:
        # DB lock check failed — proceed with process lock only (single instance)
        logger.warning("db_lock_check_failed", error=str(e))

    return True


async def release_lock():
    """Release DB distributed lock."""
    try:
        session = await get_session()
        if session is not None:
            from sqlalchemy import text
            async with session:
                await session.execute(text(
                    "DELETE FROM anchor_lock WHERE id = 'singleton' AND instance_id = :inst"
                ), {"inst": _INSTANCE_ID})
                await session.commit()
    except Exception as e:
        logger.warning("db_lock_release_failed", error=str(e))


async def check_gas_balance() -> tuple[bool, int]:
    """
    Check wallet ETH balance on Base.
    Returns (sufficient: bool, balance_wei: int).
    """
    if settings.EAS_STUB_MODE == "true":
        return True, 0

    private_key = getattr(settings, 'EAS_PRIVATE_KEY', None)
    if not private_key:
        return True, 0  # No key configured — let EAS fail naturally

    try:
        from web3 import Web3
        import os
        _USE_TESTNET = getattr(settings, 'EAS_CHAIN', 'sepolia') == 'sepolia'
        rpc = "https://sepolia.base.org" if _USE_TESTNET else os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc))
        account = w3.eth.account.from_key(private_key)

        balance = await asyncio.to_thread(w3.eth.get_balance, account.address)

        # Persist balance for monitoring
        try:
            session = await get_session()
            if session is not None:
                from sqlalchemy import text
                async with session:
                    await session.execute(text("""
                        INSERT INTO anchor_state (id, wallet_balance_wei)
                        VALUES ('singleton', :bal)
                        ON CONFLICT (id) DO UPDATE SET wallet_balance_wei = :bal
                    """), {"bal": str(balance)})
                    await session.commit()
        except Exception:
            pass

        return balance >= MIN_GAS_BALANCE_WEI, balance
    except Exception as e:
        logger.warning("gas_check_failed", error=str(e))
        return True, 0  # Can't check — proceed and let tx fail naturally


async def get_next_nonce() -> int | None:
    """
    Get reliable next nonce: max(chain_nonce, db_last_nonce + 1).
    Returns None if nonce cannot be determined (will use chain default).
    """
    if settings.EAS_STUB_MODE == "true":
        return None

    private_key = getattr(settings, 'EAS_PRIVATE_KEY', None)
    if not private_key:
        return None

    try:
        from web3 import Web3
        import os
        _USE_TESTNET = getattr(settings, 'EAS_CHAIN', 'sepolia') == 'sepolia'
        rpc = "https://sepolia.base.org" if _USE_TESTNET else os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc))
        account = w3.eth.account.from_key(private_key)

        chain_nonce = await asyncio.to_thread(
            w3.eth.get_transaction_count, account.address
        )

        # Check DB for last successful nonce
        db_nonce = None
        try:
            session = await get_session()
            if session is not None:
                from sqlalchemy import text
                async with session:
                    result = await session.execute(text(
                        "SELECT last_nonce FROM anchor_state WHERE id = 'singleton'"
                    ))
                    row = result.fetchone()
                    if row and row[0] is not None:
                        db_nonce = row[0]
        except Exception:
            pass

        if db_nonce is not None:
            return max(chain_nonce, db_nonce + 1)
        return chain_nonce

    except Exception as e:
        logger.warning("nonce_fetch_failed", error=str(e))
        return None


async def record_successful_nonce(nonce: int, tx_hash: str):
    """Record successful transaction nonce to DB."""
    try:
        session = await get_session()
        if session is not None:
            from sqlalchemy import text
            async with session:
                await session.execute(text("""
                    INSERT INTO anchor_state (id, last_nonce, last_tx_hash, last_success_at)
                    VALUES ('singleton', :nonce, :tx, NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET last_nonce = :nonce, last_tx_hash = :tx, last_success_at = NOW()
                """), {"nonce": nonce, "tx": tx_hash})
                await session.commit()
    except Exception as e:
        logger.warning("nonce_record_failed", error=str(e))


async def mark_batch_retry(batch_id: str, error_msg: str):
    """Mark a batch for retry with error details."""
    try:
        from ..db.models import Batch
        session = await get_session()
        if session is None:
            return
        from sqlalchemy import select
        async with session:
            result = await session.execute(
                select(Batch).where(Batch.batch_id == batch_id)
            )
            batch = result.scalar_one_or_none()
            if batch:
                batch.retry_count = (batch.retry_count or 0) + 1
                batch.last_retry_at = datetime.now(timezone.utc)
                batch.error_message = error_msg
                if batch.retry_count >= MAX_RETRY_COUNT:
                    batch.status = "anchor_failed"
                    logger.error("batch_anchor_failed_permanently",
                                 batch_id=batch_id, retries=batch.retry_count)
                else:
                    batch.status = "retry_queued"
                    logger.info("batch_retry_queued",
                                batch_id=batch_id, retry=batch.retry_count)
                await session.commit()
    except Exception as e:
        logger.warning("batch_retry_mark_failed", batch_id=batch_id, error=str(e))


def should_retry_batch(batch: dict) -> bool:
    """Check if a batch should be retried based on retry count."""
    return (batch.get("retry_count") or 0) < MAX_RETRY_COUNT
