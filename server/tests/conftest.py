"""Ensure server/app is importable when running tests from repo root."""
import os
import sys
from pathlib import Path

# Set test environment variables BEFORE any app imports
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LLACHAT_INTERNAL_TOKEN", "test-internal-token-for-e2e")
os.environ.setdefault("EAS_STUB_MODE", "true")
# Test-only: lower anchor thresholds so single-batch tests can exercise the
# full anchor path. Production defaults (MIN_ANCHOR_BATCHES=10, RECORDS=100)
# exist to prevent gas-waste from tiny/cheap batches — they are irrelevant
# in a test harness that anchors deterministic stub attestations.
os.environ.setdefault("MIN_ANCHOR_BATCHES", "1")
os.environ.setdefault("MIN_ANCHOR_RECORDS", "1")
os.environ.setdefault("SUPER_BATCH_MIN_SIZE", "1")

# Add server/ to sys.path so `from app.main import app` works
server_dir = str(Path(__file__).resolve().parent.parent)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
