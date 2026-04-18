"""
ATLAST ECP — Evidence Chain Protocol

The open standard for recording, chaining, and verifying AI Agent actions.

Quick start (zero code):
    $ atlast run python my_agent.py

Quick start (1 line):
    from atlast_ecp import wrap
    client = wrap(Anthropic())

Quick start (minimal):
    from atlast_ecp import record_minimal
    record_minimal("hello prompt", "agent response", agent="my-agent")
"""

from .wrap import wrap
from .core import record, record_async, record_minimal, record_minimal_async, get_identity, reset
from .auto import init
from .identity import get_or_create_identity
from .record import create_record, create_minimal_record, record_to_dict
from .storage import save_record, load_records, load_record_by_id
from .signals import detect_flags, compute_trust_signals
from .batch import trigger_batch_upload, run_batch, start_scheduler
from .verify import (
    verify_signature,
    verify_merkle_proof,
    build_merkle_proof,
    verify_record,
    verify_record_with_key,
)
from .config import get_api_url, get_api_key, load_config, save_config

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("atlast-ecp")
except Exception:
    # Running from source without pip install metadata — honest fallback.
    # Never hardcode a numeric version here: it drifts from pyproject.toml
    # and lies to telemetry. "unknown" is better than wrong.
    __version__ = "unknown"
__all__ = [
    # Core
    "wrap",
    "init",
    "record",
    "record_async",
    "record_minimal",
    "record_minimal_async",
    "get_identity",
    "reset",
    # Identity
    "get_or_create_identity",
    # Records
    "create_record",
    "create_minimal_record",
    "record_to_dict",
    # Storage
    "save_record",
    "load_records",
    "load_record_by_id",
    # Signals
    "detect_flags",
    "compute_trust_signals",
    # Batch
    "trigger_batch_upload",
    "run_batch",
    "start_scheduler",
    # Verification (public API for any ECP-compatible backend)
    "verify_signature",
    "verify_merkle_proof",
    "build_merkle_proof",
    "verify_record",
    "verify_record_with_key",
    # Config
    "get_api_url",
    "get_api_key",
    "load_config",
    "save_config",
]

# Query & Audit
from .query import search, trace, audit, timeline, rebuild_index
