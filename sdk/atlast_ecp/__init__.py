"""
ATLAST ECP — Evidence Chain Protocol SDK

Usage:
    from atlast_ecp import wrap
    from anthropic import Anthropic

    client = wrap(Anthropic())
    # That's it. Passive recording starts immediately.
"""

from .wrap import wrap
from .core import record, record_async, get_identity, reset
from .auto import init
from .identity import get_or_create_identity
from .record import create_record, record_to_dict
from .storage import save_record, load_records, load_record_by_id
from .signals import detect_flags, compute_trust_signals
from .batch import trigger_batch_upload, run_batch, start_scheduler

__version__ = "0.3.0"
__all__ = [
    "wrap",
    "init",
    "record",
    "record_async",
    "get_identity",
    "reset",
    "get_or_create_identity",
    "create_record",
    "record_to_dict",
    "save_record",
    "load_records",
    "load_record_by_id",
    "detect_flags",
    "compute_trust_signals",
    "trigger_batch_upload",
    "run_batch",
    "start_scheduler",
]
