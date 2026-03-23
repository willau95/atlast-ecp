"""Ensure server/app is importable when running tests from repo root."""
import sys
from pathlib import Path

# Add server/ to sys.path so `from app.main import app` works
server_dir = str(Path(__file__).resolve().parent.parent)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
