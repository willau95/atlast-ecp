"""
ATLAST ECP AutoGen Adapter — one-line ECP recording for Microsoft AutoGen agents.

Usage:
    from atlast_ecp.adapters.autogen import register_atlast
    register_atlast(my_agent)

Supports AutoGen v0.2+ ConversableAgent. Records are generated for each
agent reply, and multi-agent message passing is detected for A2A handoff records.

Zero dependency: AutoGen is imported at runtime only.
Privacy: only SHA-256 hashes are recorded, never raw content.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

# Runtime import — no hard dependency on AutoGen
try:
    from autogen import ConversableAgent
    HAS_AUTOGEN = True
except ImportError:
    try:
        from autogen.agentchat import ConversableAgent
        HAS_AUTOGEN = True
    except ImportError:
        HAS_AUTOGEN = False
        ConversableAgent = object  # type: ignore


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


class ATLASTAutoGenMiddleware:
    """
    Middleware that wraps an AutoGen ConversableAgent to record ECP evidence.

    Records:
    - Each generate_reply call as an ECP record
    - Cross-agent messages as A2A handoff records (meta.handoff=true)
    """

    def __init__(self, agent_id: str = "autogen-agent", storage_dir: Optional[str] = None):
        self.agent_id = agent_id
        self._storage_dir = storage_dir
        self._records: list[dict] = []

    def _create_record(
        self,
        action: str,
        input_text: str,
        output_text: str,
        duration_ms: int = 0,
        meta_extra: Optional[dict] = None,
    ) -> dict:
        """Create an ECP v1.0 record."""
        from ..record import create_minimal_record

        meta = {"duration_ms": duration_ms}
        if meta_extra:
            meta.update(meta_extra)

        try:
            rec = create_minimal_record(
                agent=self.agent_id,
                action=action,
                in_content=input_text,
                out_content=output_text,
            )
            rec["meta"] = meta
            self._records.append(rec)
            return rec
        except Exception:
            # Fail-open: never crash the agent
            return {}

    @property
    def records(self) -> list[dict]:
        return list(self._records)

    def wrap(self, agent: Any) -> Any:
        """
        Wrap a ConversableAgent to record ECP evidence on each reply.
        Returns the same agent (mutated).
        """
        if not hasattr(agent, "generate_reply"):
            return agent

        original_generate = agent.generate_reply

        middleware = self

        def patched_generate_reply(
            messages: Optional[list[dict]] = None,
            sender: Optional[Any] = None,
            **kwargs: Any,
        ) -> Any:
            start = time.time()
            result = original_generate(messages=messages, sender=sender, **kwargs)
            duration_ms = int((time.time() - start) * 1000)

            # Build input text from messages
            input_text = ""
            if messages:
                input_text = str(messages[-1].get("content", "")) if messages else ""

            output_text = str(result) if result else ""

            # Detect cross-agent communication
            meta_extra: dict[str, Any] = {}
            sender_name = getattr(sender, "name", None) if sender else None
            agent_name = getattr(agent, "name", None)

            if sender_name and agent_name and sender_name != agent_name:
                meta_extra["handoff"] = True
                meta_extra["source_agent"] = sender_name
                meta_extra["target_agent"] = agent_name
                action = "autogen_handoff"
            else:
                action = "autogen_reply"

            middleware._create_record(
                action=action,
                input_text=input_text,
                output_text=output_text,
                duration_ms=duration_ms,
                meta_extra=meta_extra,
            )

            return result

        agent.generate_reply = patched_generate_reply
        return agent


def register_atlast(
    agent: Any,
    agent_id: Optional[str] = None,
    storage_dir: Optional[str] = None,
) -> ATLASTAutoGenMiddleware:
    """
    One-line registration: register_atlast(my_agent)

    Args:
        agent: AutoGen ConversableAgent instance
        agent_id: Custom agent identifier (default: agent.name or "autogen-agent")
        storage_dir: Custom storage directory

    Returns:
        ATLASTAutoGenMiddleware instance (for accessing records)
    """
    name = agent_id or getattr(agent, "name", None) or "autogen-agent"
    middleware = ATLASTAutoGenMiddleware(agent_id=name, storage_dir=storage_dir)
    middleware.wrap(agent)
    return middleware
