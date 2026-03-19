"""
ECP Reference Server — Authentication

Validates X-Agent-Key header against stored agent API keys.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from . import database as db


def verify_agent_key(x_agent_key: str = Header(..., alias="X-Agent-Key")) -> dict:
    """FastAPI dependency: validates X-Agent-Key and returns agent dict."""
    if not x_agent_key or not x_agent_key.startswith("atl_"):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    agent = db.get_agent_by_key(x_agent_key)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return agent
