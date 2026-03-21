"""
ATLAST ECP — LangChain Callback Handler

One-line integration for LangChain LLMs, Chains, and Agents.

Usage:
    from atlast_ecp.adapters.langchain import ATLASTCallbackHandler

    # With ChatOpenAI
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4", callbacks=[ATLASTCallbackHandler(agent="my-agent")])

    # With any chain
    chain = prompt | llm | parser
    chain.invoke({"question": "..."}, config={"callbacks": [ATLASTCallbackHandler()]})

    # With AgentExecutor
    agent = AgentExecutor(agent=..., tools=..., callbacks=[ATLASTCallbackHandler()])

Captures: LLM calls, tool calls, chain runs, retriever queries.
All content is SHA-256 hashed locally — nothing leaves your device.
Fail-Open: adapter errors never affect your agent.
"""

from __future__ import annotations

import time
import json
from typing import Any, Optional, Union
from uuid import UUID

# LangChain is an optional dependency — import at runtime
try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.outputs import LLMResult, ChatResult

    HAS_LANGCHAIN = True
except ImportError:
    try:
        # Fallback for older langchain versions
        from langchain.callbacks.base import BaseCallbackHandler
        from langchain.schema import LLMResult

        HAS_LANGCHAIN = True
    except ImportError:
        HAS_LANGCHAIN = False
        # Create a stub so the class definition doesn't fail
        BaseCallbackHandler = object


class ATLASTCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that records ECP evidence for every LLM/tool call.

    Args:
        agent: Agent identifier string (default: "langchain-agent")
        verbose: Print ECP record IDs to stdout (default: False)
    """

    def __init__(self, agent: str = "langchain-agent", verbose: bool = False):
        if HAS_LANGCHAIN:
            super().__init__()
        self.agent = agent
        self.verbose = verbose
        # Track in-flight calls: run_id → {start_time, input, ...}
        self._inflight: dict[str, dict] = {}
        self._record_count = 0

    @property
    def record_count(self) -> int:
        return self._record_count

    # ─── LLM Callbacks ────────────────────────────────────────────────────

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts generating."""
        try:
            self._inflight[str(run_id)] = {
                "start": time.time(),
                "input": "\n".join(prompts) if prompts else "",
                "action": "llm_call",
                "model": serialized.get("kwargs", {}).get("model_name")
                    or serialized.get("kwargs", {}).get("model")
                    or kwargs.get("invocation_params", {}).get("model")
                    or kwargs.get("invocation_params", {}).get("model_name")
                    or "unknown",
            }
        except Exception:
            pass  # Fail-Open

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when chat model starts (ChatOpenAI, etc.)."""
        try:
            # Flatten messages to text
            msg_text = []
            for msg_list in messages:
                for msg in msg_list:
                    if hasattr(msg, "content"):
                        msg_text.append(f"{getattr(msg, 'type', 'unknown')}: {msg.content}")
                    elif isinstance(msg, dict):
                        msg_text.append(f"{msg.get('role', 'unknown')}: {msg.get('content', '')}")
                    else:
                        msg_text.append(str(msg))

            model = (
                serialized.get("kwargs", {}).get("model_name")
                or serialized.get("kwargs", {}).get("model")
                or kwargs.get("invocation_params", {}).get("model")
                or kwargs.get("invocation_params", {}).get("model_name")
                or "unknown"
            )

            self._inflight[str(run_id)] = {
                "start": time.time(),
                "input": "\n".join(msg_text),
                "action": "llm_call",
                "model": model,
            }
        except Exception:
            pass  # Fail-Open

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM finishes — record the ECP evidence."""
        try:
            info = self._inflight.pop(str(run_id), None)
            if not info:
                return

            latency_ms = int((time.time() - info["start"]) * 1000)

            # Extract output text
            output = ""
            tokens_in = None
            tokens_out = None
            if hasattr(response, "generations"):
                for gen_list in response.generations:
                    for gen in gen_list:
                        if hasattr(gen, "text"):
                            output += gen.text
                        elif hasattr(gen, "message") and hasattr(gen.message, "content"):
                            output += gen.message.content
            if hasattr(response, "llm_output") and response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                tokens_in = usage.get("prompt_tokens")
                tokens_out = usage.get("completion_tokens")

            self._do_record(
                input_content=info["input"],
                output_content=output,
                action=info["action"],
                model=info.get("model"),
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        except Exception:
            pass  # Fail-Open

    def on_llm_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Record failed LLM calls too."""
        try:
            info = self._inflight.pop(str(run_id), None)
            if not info:
                return
            latency_ms = int((time.time() - info["start"]) * 1000)
            self._do_record(
                input_content=info["input"],
                output_content=f"ERROR: {type(error).__name__}: {error}",
                action=info["action"],
                model=info.get("model"),
                latency_ms=latency_ms,
            )
        except Exception:
            pass

    # ─── Tool Callbacks ───────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        try:
            tool_name = serialized.get("name", "unknown_tool")
            self._inflight[str(run_id)] = {
                "start": time.time(),
                "input": f"[{tool_name}] {input_str}",
                "action": "tool_call",
                "tool_name": tool_name,
            }
        except Exception:
            pass

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        try:
            info = self._inflight.pop(str(run_id), None)
            if not info:
                return
            latency_ms = int((time.time() - info["start"]) * 1000)
            self._do_record(
                input_content=info["input"],
                output_content=str(output),
                action="tool_call",
                latency_ms=latency_ms,
            )
        except Exception:
            pass

    def on_tool_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        try:
            info = self._inflight.pop(str(run_id), None)
            if not info:
                return
            latency_ms = int((time.time() - info["start"]) * 1000)
            self._do_record(
                input_content=info["input"],
                output_content=f"ERROR: {type(error).__name__}: {error}",
                action="tool_call",
                latency_ms=latency_ms,
            )
        except Exception:
            pass

    # ─── Retriever Callbacks ──────────────────────────────────────────────

    def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        try:
            self._inflight[str(run_id)] = {
                "start": time.time(),
                "input": query,
                "action": "tool_call",
            }
        except Exception:
            pass

    def on_retriever_end(
        self,
        documents: list[Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        try:
            info = self._inflight.pop(str(run_id), None)
            if not info:
                return
            latency_ms = int((time.time() - info["start"]) * 1000)
            # Summarize retrieved docs
            doc_texts = []
            for doc in documents:
                if hasattr(doc, "page_content"):
                    doc_texts.append(doc.page_content[:200])
                else:
                    doc_texts.append(str(doc)[:200])
            output = f"Retrieved {len(documents)} documents: " + " | ".join(doc_texts)
            self._do_record(
                input_content=info["input"],
                output_content=output,
                action="tool_call",
                latency_ms=latency_ms,
            )
        except Exception:
            pass

    # ─── Internal ─────────────────────────────────────────────────────────

    def _do_record(self, input_content, output_content, action="llm_call",
                   model=None, latency_ms=0, tokens_in=None, tokens_out=None):
        """Create and save an ECP record. Fail-Open."""
        try:
            from atlast_ecp.core import record_minimal
            rid = record_minimal(
                input_content=input_content,
                output_content=output_content,
                agent=self.agent,
                action=action,
                model=model,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
            self._record_count += 1
            if self.verbose and rid:
                print(f"[ATLAST ECP] {rid}")
        except Exception:
            pass  # Fail-Open: never crash the agent
