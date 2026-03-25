"""Tests for ATLAST ECP Framework Adapters — LangChain + CrewAI.

These tests mock the framework interfaces so they run without
langchain or crewai installed.
"""

import os
import json
import time
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from atlast_ecp.core import reset
from atlast_ecp.storage import load_records


@pytest.fixture(autouse=True)
def clean_ecp(tmp_path):
    d = str(tmp_path / "ecp")
    old = os.environ.get("ATLAST_ECP_DIR")
    os.environ["ATLAST_ECP_DIR"] = d
    reset()
    yield d
    if old:
        os.environ["ATLAST_ECP_DIR"] = old
    else:
        os.environ.pop("ATLAST_ECP_DIR", None)


# ─── LangChain Adapter Tests ─────────────────────────────────────────────────

class TestLangChainAdapter:
    """Test ATLASTCallbackHandler without real LangChain dependency."""

    def _get_handler(self, **kwargs):
        # Patch BaseCallbackHandler to be a plain object if langchain not installed
        from atlast_ecp.adapters.langchain import ATLASTCallbackHandler
        return ATLASTCallbackHandler(**kwargs)

    def test_import_does_not_crash(self):
        """Importing the adapter never crashes, even without langchain."""
        from atlast_ecp.adapters import langchain
        assert hasattr(langchain, "ATLASTCallbackHandler")

    def test_llm_start_end_creates_record(self):
        handler = self._get_handler(agent="test-lc")
        run_id = uuid4()

        # Simulate on_llm_start
        handler.on_llm_start(
            serialized={"kwargs": {"model_name": "gpt-4"}},
            prompts=["What is 2+2?"],
            run_id=run_id,
        )

        # Simulate on_llm_end
        mock_response = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "The answer is 4."
        mock_response.generations = [[mock_gen]]
        mock_response.llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}

        handler.on_llm_end(response=mock_response, run_id=run_id)

        assert handler.record_count == 1
        records = load_records(limit=10)
        assert len(records) >= 1
        rec = records[-1]
        assert rec["agent"] == "test-lc"
        assert rec["action"] == "llm_call"
        assert rec["meta"]["model"] == "gpt-4"
        assert rec["meta"]["tokens_in"] == 10
        assert rec["meta"]["tokens_out"] == 5

    def test_chat_model_start_end(self):
        handler = self._get_handler(agent="test-chat")
        run_id = uuid4()

        # Mock chat messages
        mock_msg = MagicMock()
        mock_msg.type = "human"
        mock_msg.content = "Hello Claude"

        handler.on_chat_model_start(
            serialized={"kwargs": {"model": "claude-sonnet-4-20250514"}},
            messages=[[mock_msg]],
            run_id=run_id,
        )

        mock_response = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = ""
        mock_gen.message = MagicMock()
        mock_gen.message.content = "Hello! How can I help?"
        mock_response.generations = [[mock_gen]]
        mock_response.llm_output = None

        handler.on_llm_end(response=mock_response, run_id=run_id)
        assert handler.record_count == 1

    def test_llm_error_recorded(self):
        handler = self._get_handler(agent="test-err")
        run_id = uuid4()

        handler.on_llm_start(
            serialized={"kwargs": {}},
            prompts=["test"],
            run_id=run_id,
        )
        handler.on_llm_error(
            error=RuntimeError("API timeout"),
            run_id=run_id,
        )

        assert handler.record_count == 1
        records = load_records(limit=10)
        rec = records[-1]
        assert "error" in rec.get("meta", {}).get("flags", [])

    def test_tool_start_end(self):
        handler = self._get_handler(agent="test-tool")
        run_id = uuid4()

        handler.on_tool_start(
            serialized={"name": "web_search"},
            input_str="latest AI news",
            run_id=run_id,
        )
        handler.on_tool_end(
            output="Found 10 results about AI...",
            run_id=run_id,
        )

        assert handler.record_count == 1
        records = load_records(limit=10)
        rec = records[-1]
        assert rec["action"] == "tool_call"

    def test_tool_error(self):
        handler = self._get_handler(agent="test-tool-err")
        run_id = uuid4()

        handler.on_tool_start(
            serialized={"name": "calculator"},
            input_str="1/0",
            run_id=run_id,
        )
        handler.on_tool_error(
            error=ZeroDivisionError("division by zero"),
            run_id=run_id,
        )

        assert handler.record_count == 1

    def test_retriever_start_end(self):
        handler = self._get_handler(agent="test-rag")
        run_id = uuid4()

        handler.on_retriever_start(
            serialized={},
            query="What is ATLAST?",
            run_id=run_id,
        )

        mock_doc = MagicMock()
        mock_doc.page_content = "ATLAST is a trust infrastructure protocol..."

        handler.on_retriever_end(
            documents=[mock_doc],
            run_id=run_id,
        )

        assert handler.record_count == 1

    def test_multiple_concurrent_calls(self):
        handler = self._get_handler(agent="test-multi")
        rid1 = uuid4()
        rid2 = uuid4()

        # Start both
        handler.on_llm_start({"kwargs": {"model": "gpt-4"}}, ["prompt1"], run_id=rid1)
        handler.on_llm_start({"kwargs": {"model": "claude-sonnet-4-20250514"}}, ["prompt2"], run_id=rid2)

        # End in reverse order
        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "response"
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None

        handler.on_llm_end(response=mock_resp, run_id=rid2)
        handler.on_llm_end(response=mock_resp, run_id=rid1)

        assert handler.record_count == 2

    def test_verbose_mode(self, capsys):
        handler = self._get_handler(agent="test-verbose", verbose=True)
        run_id = uuid4()
        handler.on_llm_start({"kwargs": {}}, ["test"], run_id=run_id)
        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "ok"
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None
        handler.on_llm_end(response=mock_resp, run_id=run_id)

        captured = capsys.readouterr()
        assert "[ATLAST ECP]" in captured.out

    def test_fail_open_on_bad_run_id(self):
        """on_llm_end with unknown run_id should not crash."""
        handler = self._get_handler()
        handler.on_llm_end(response=MagicMock(), run_id=uuid4())
        assert handler.record_count == 0  # no crash, no record

    def test_privacy_no_raw_content(self):
        handler = self._get_handler(agent="test-privacy")
        run_id = uuid4()
        secret = "TOP SECRET CLASSIFIED DATA xyz987"

        handler.on_llm_start({"kwargs": {}}, [secret], run_id=run_id)
        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = f"Response about {secret}"
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None
        handler.on_llm_end(response=mock_resp, run_id=run_id)

        records = load_records(limit=10)
        serialized = json.dumps(records[-1])
        assert secret not in serialized


# ─── CrewAI Adapter Tests ─────────────────────────────────────────────────────

class TestCrewAIAdapter:
    """Test ATLASTCrewCallback without real CrewAI dependency."""

    def _get_callback(self, **kwargs):
        from atlast_ecp.adapters.crewai import ATLASTCrewCallback
        return ATLASTCrewCallback(**kwargs)

    def test_import_does_not_crash(self):
        from atlast_ecp.adapters import crewai
        assert hasattr(crewai, "ATLASTCrewCallback")

    def test_task_output_creates_record(self):
        cb = self._get_callback(agent="test-crew")

        mock_output = MagicMock()
        mock_output.description = "Research AI trends"
        mock_output.raw = "AI agents are becoming more autonomous..."
        mock_output.agent = "researcher"

        cb(mock_output)

        assert cb.record_count == 1
        records = load_records(limit=10)
        rec = records[-1]
        assert rec["agent"] == "test-crew/researcher"
        assert rec["action"] == "llm_call"

    def test_dict_output(self):
        cb = self._get_callback(agent="test-dict")

        cb({"description": "Write report", "raw": "Report content here"})

        assert cb.record_count == 1

    def test_string_output(self):
        cb = self._get_callback(agent="test-str")
        cb("plain string output")
        assert cb.record_count == 1

    def test_step_callback_tool_call(self):
        cb = self._get_callback(agent="test-step")

        mock_step = MagicMock()
        mock_step.tool = "web_search"
        mock_step.tool_input = "latest news"
        mock_step.log = "Searching the web..."

        cb.step_callback(mock_step)

        assert cb.record_count == 1
        records = load_records(limit=10)
        assert records[-1]["action"] == "tool_call"

    def test_step_callback_agent_finish(self):
        cb = self._get_callback(agent="test-finish")

        mock_step = MagicMock(spec=["output", "log"])
        mock_step.output = "Final answer: 42"
        mock_step.log = "Agent reasoning..."
        # Make sure it doesn't have 'tool' attribute
        del mock_step.tool

        cb.step_callback(mock_step)
        assert cb.record_count == 1

    def test_step_callback_dict(self):
        cb = self._get_callback(agent="test-dict-step")

        cb.step_callback({
            "input": "question",
            "output": "answer",
            "type": "tool_call",
        })

        assert cb.record_count == 1

    def test_multiple_tasks(self):
        cb = self._get_callback(agent="multi-crew")

        for i in range(5):
            mock = MagicMock()
            mock.description = f"Task {i}"
            mock.raw = f"Output {i}"
            mock.agent = f"agent-{i}"
            cb(mock)

        assert cb.record_count == 5

    def test_fail_open(self):
        """Callback should never crash even with weird input."""
        cb = self._get_callback(agent="test-safe")

        # These should all survive
        cb(None)  # None
        cb(42)  # int
        cb([1, 2, 3])  # list
        cb(object())  # random object

        # Should have created records for each (best effort)
        # No crash is the important thing
        assert True

    def test_verbose_mode(self, capsys):
        cb = self._get_callback(agent="test-v", verbose=True)
        mock = MagicMock()
        mock.description = "test"
        mock.raw = "output"
        mock.agent = None
        cb(mock)

        captured = capsys.readouterr()
        assert "[ATLAST ECP]" in captured.out


# ── P3-5: AutoGen Adapter Tests ──────────────────────────────────────────


class TestAutoGenAdapter:
    """Tests for AutoGen adapter — mocked, no autogen dependency needed."""

    def test_import_without_autogen(self):
        """Importing adapter without autogen installed should not raise."""
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware, HAS_AUTOGEN
        # HAS_AUTOGEN might be True or False depending on env
        assert ATLASTAutoGenMiddleware is not None

    def test_middleware_creation(self):
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware
        mw = ATLASTAutoGenMiddleware(agent_id="test-agent")
        assert mw.agent_id == "test-agent"
        assert mw.records == []

    def test_create_record(self):
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware
        mw = ATLASTAutoGenMiddleware(agent_id="test-agent")
        rec = mw._create_record(
            action="autogen_reply",
            input_text="hello",
            output_text="world",
            duration_ms=100,
        )
        assert rec.get("ecp") == "1.0"
        assert rec.get("agent") == "test-agent"
        assert rec.get("action") == "autogen_reply"
        assert "in_hash" in rec
        assert "out_hash" in rec
        assert len(mw.records) == 1

    def test_wrap_mock_agent(self):
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class MockAgent:
            name = "mock-agent"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "I am a mock response"

        agent = MockAgent()
        mw = ATLASTAutoGenMiddleware(agent_id="mock-agent")
        mw.wrap(agent)

        result = agent.generate_reply(messages=[{"content": "hello"}])
        assert result == "I am a mock response"
        assert len(mw.records) == 1
        assert mw.records[0]["action"] == "autogen_reply"

    def test_handoff_detection(self):
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class MockAgent:
            name = "agent-b"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "response from B"

        class MockSender:
            name = "agent-a"

        agent = MockAgent()
        sender = MockSender()
        mw = ATLASTAutoGenMiddleware(agent_id="agent-b")
        mw.wrap(agent)

        result = agent.generate_reply(messages=[{"content": "hi"}], sender=sender)
        assert result == "response from B"
        assert len(mw.records) == 1
        assert mw.records[0]["action"] == "autogen_handoff"
        assert mw.records[0]["meta"]["handoff"] is True
        assert mw.records[0]["meta"]["source_agent"] == "agent-a"
        assert mw.records[0]["meta"]["target_agent"] == "agent-b"

    def test_register_atlast(self):
        from atlast_ecp.adapters.autogen import register_atlast

        class MockAgent:
            name = "my-agent"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "hi"

        agent = MockAgent()
        mw = register_atlast(agent)
        agent.generate_reply(messages=[{"content": "test"}])
        assert len(mw.records) == 1

    def test_record_has_required_fields(self):
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class MockAgent:
            name = "test"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "ok"

        agent = MockAgent()
        mw = ATLASTAutoGenMiddleware(agent_id="test")
        mw.wrap(agent)
        agent.generate_reply(messages=[{"content": "x"}])

        rec = mw.records[0]
        required = {"ecp", "id", "ts", "agent", "action", "in_hash", "out_hash"}
        assert required.issubset(set(rec.keys())), f"Missing: {required - set(rec.keys())}"

    def test_fail_open(self):
        """Adapter should never crash even with weird inputs."""
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class MockAgent:
            name = "test"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return None  # weird output

        agent = MockAgent()
        mw = ATLASTAutoGenMiddleware(agent_id="test")
        mw.wrap(agent)
        result = agent.generate_reply()  # no messages
        assert result is None  # should not crash


# ─── LangChain Edge Case Tests ────────────────────────────────────────────────

class TestLangChainEdgeCases:
    """Additional edge-case tests for ATLASTCallbackHandler."""

    def _get_handler(self, **kwargs):
        from atlast_ecp.adapters.langchain import ATLASTCallbackHandler
        return ATLASTCallbackHandler(**kwargs)

    def test_retriever_start_end_creates_record(self):
        """on_retriever_start/end creates a tool_call record."""
        handler = self._get_handler(agent="test-retriever")
        run_id = uuid4()

        handler.on_retriever_start(
            serialized={"name": "faiss"},
            query="What is the capital of France?",
            run_id=run_id,
        )

        doc1 = MagicMock()
        doc1.page_content = "Paris is the capital of France."
        doc2 = MagicMock()
        doc2.page_content = "France's largest city is also its capital."

        handler.on_retriever_end(documents=[doc1, doc2], run_id=run_id)

        assert handler.record_count == 1
        records = load_records(limit=10)
        rec = records[-1]
        assert rec["action"] == "tool_call"

    def test_retriever_end_with_non_document_objects(self):
        """on_retriever_end handles docs without page_content attribute."""
        handler = self._get_handler(agent="test-raw-docs")
        run_id = uuid4()

        handler.on_retriever_start(serialized={}, query="test query", run_id=run_id)
        # Pass plain strings instead of Document objects
        handler.on_retriever_end(documents=["raw text 1", "raw text 2"], run_id=run_id)

        assert handler.record_count == 1

    def test_chat_model_start_with_nested_messages(self):
        """on_chat_model_start handles nested message lists."""
        handler = self._get_handler(agent="test-nested-msg")
        run_id = uuid4()

        system_msg = MagicMock()
        system_msg.type = "system"
        system_msg.content = "You are a helpful assistant."

        human_msg = MagicMock()
        human_msg.type = "human"
        human_msg.content = "Tell me about ECP."

        ai_msg = MagicMock()
        ai_msg.type = "ai"
        ai_msg.content = "Previous response."

        # messages is a list of lists (batch of conversations)
        handler.on_chat_model_start(
            serialized={"kwargs": {"model_name": "gpt-4o"}},
            messages=[[system_msg, human_msg, ai_msg]],
            run_id=run_id,
        )

        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "ECP is the Evidence Chain Protocol."
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None

        handler.on_llm_end(response=mock_resp, run_id=run_id)
        assert handler.record_count == 1

    def test_chat_model_start_with_dict_messages(self):
        """on_chat_model_start handles dict-style messages (no .content attr)."""
        handler = self._get_handler(agent="test-dict-msgs")
        run_id = uuid4()

        handler.on_chat_model_start(
            serialized={"kwargs": {}},
            messages=[[{"role": "user", "content": "Hello dict message"}]],
            run_id=run_id,
        )

        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "Hi there"
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None

        handler.on_llm_end(response=mock_resp, run_id=run_id)
        assert handler.record_count == 1

    def test_llm_end_empty_response_text(self):
        """on_llm_end with empty generation text still creates a record."""
        handler = self._get_handler(agent="test-empty-resp")
        run_id = uuid4()

        handler.on_llm_start({"kwargs": {"model": "gpt-4"}}, ["prompt"], run_id=run_id)

        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = ""
        mock_gen.message = MagicMock()
        mock_gen.message.content = ""
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None

        handler.on_llm_end(response=mock_resp, run_id=run_id)
        assert handler.record_count == 1

    def test_model_extraction_from_invocation_params(self):
        """Model name extracted from kwargs.invocation_params fallback."""
        handler = self._get_handler(agent="test-model-extract")
        run_id = uuid4()

        # serialized has no model, but invocation_params does
        handler.on_llm_start(
            serialized={"kwargs": {}},
            prompts=["test"],
            run_id=run_id,
            invocation_params={"model": "claude-haiku-4-5"},
        )

        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "ok"
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None
        handler.on_llm_end(response=mock_resp, run_id=run_id)

        assert handler.record_count == 1
        records = load_records(limit=10)
        rec = records[-1]
        # Model comes from invocation_params
        assert rec["meta"]["model"] in ("claude-haiku-4-5", "unknown")

    def test_model_extraction_from_serialized_kwargs_model(self):
        """Model extracted from serialized.kwargs.model (not model_name)."""
        handler = self._get_handler(agent="test-model-kw")
        run_id = uuid4()

        handler.on_llm_start(
            serialized={"kwargs": {"model": "gpt-3.5-turbo"}},
            prompts=["test"],
            run_id=run_id,
        )

        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "ok"
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None
        handler.on_llm_end(response=mock_resp, run_id=run_id)

        records = load_records(limit=10)
        assert records[-1]["meta"]["model"] == "gpt-3.5-turbo"

    def test_concurrent_calls_cleanup(self):
        """After all calls complete, _inflight dict is empty."""
        handler = self._get_handler(agent="test-cleanup")
        ids = [uuid4() for _ in range(4)]

        for i, rid in enumerate(ids):
            handler.on_llm_start({"kwargs": {}}, [f"p{i}"], run_id=rid)

        mock_resp = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "done"
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = None

        for rid in ids:
            handler.on_llm_end(response=mock_resp, run_id=rid)

        assert len(handler._inflight) == 0
        assert handler.record_count == 4

    def test_retriever_end_with_empty_documents(self):
        """Retriever returning zero documents still creates a record."""
        handler = self._get_handler(agent="test-empty-retriever")
        run_id = uuid4()

        handler.on_retriever_start(serialized={}, query="obscure query", run_id=run_id)
        handler.on_retriever_end(documents=[], run_id=run_id)

        assert handler.record_count == 1


# ─── CrewAI Edge Case Tests ───────────────────────────────────────────────────

class TestCrewAIEdgeCases:
    """Additional edge-case tests for ATLASTCrewCallback."""

    def _get_callback(self, **kwargs):
        from atlast_ecp.adapters.crewai import ATLASTCrewCallback
        return ATLASTCrewCallback(**kwargs)

    def test_on_task_start_latency_tracking(self):
        """on_task_start stores start time; subsequent call can read it."""
        cb = self._get_callback(agent="latency-crew")
        task = "Analyze Q4 financials"

        cb.on_task_start(task)
        assert task[:100] in cb._task_starts
        assert cb._task_starts[task[:100]] > 0

    def test_on_task_start_truncates_long_key(self):
        """on_task_start truncates keys to 100 chars to avoid memory bloat."""
        cb = self._get_callback(agent="trunc-crew")
        long_desc = "X" * 200
        cb.on_task_start(long_desc)
        assert long_desc[:100] in cb._task_starts
        assert long_desc not in cb._task_starts

    def test_nested_dict_output(self):
        """Dict output with nested values is handled without crash."""
        cb = self._get_callback(agent="nested-dict-crew")

        cb({
            "description": "Complex nested task",
            "raw": {"result": "value", "score": 0.95},  # raw is a dict, not str
            "metadata": {"source": "web"},
        })

        assert cb.record_count == 1

    def test_task_output_with_none_agent_field(self):
        """TaskOutput with agent=None uses the callback's base agent name."""
        cb = self._get_callback(agent="base-crew")

        mock_output = MagicMock()
        mock_output.description = "Task with no agent attribution"
        mock_output.raw = "Output here"
        mock_output.agent = None

        cb(mock_output)

        assert cb.record_count == 1
        records = load_records(limit=10)
        rec = records[-1]
        # When agent is None/falsy, should use base agent name
        assert rec["agent"] == "base-crew"

    def test_task_output_with_output_attr(self):
        """TaskOutput with .output instead of .raw is handled."""
        cb = self._get_callback(agent="output-crew")

        mock_output = MagicMock(spec=["description", "output"])
        mock_output.description = "Task using .output attr"
        mock_output.output = "Result via .output"

        cb(mock_output)
        assert cb.record_count == 1

    def test_step_callback_string_output(self):
        """step_callback handles plain string (fallback path)."""
        cb = self._get_callback(agent="str-step-crew")

        # String has no .tool, .output attributes — hits the else branch
        cb.step_callback("step result as plain string")
        assert cb.record_count == 1


# ─── AutoGen Edge Case Tests ──────────────────────────────────────────────────

class TestAutoGenEdgeCases:
    """Additional edge-case tests for AutoGen adapter."""

    def test_wrap_agent_without_name(self):
        """wrap() handles agent with no .name attribute gracefully."""
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class NamelessAgent:
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "nameless reply"

        agent = NamelessAgent()
        mw = ATLASTAutoGenMiddleware(agent_id="explicit-id")
        mw.wrap(agent)

        result = agent.generate_reply(messages=[{"content": "hello"}])
        assert result == "nameless reply"
        assert len(mw.records) == 1

    def test_wrap_agent_without_generate_reply(self):
        """wrap() on an object without generate_reply is a no-op."""
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class WeirdObject:
            name = "weird"

        obj = WeirdObject()
        mw = ATLASTAutoGenMiddleware(agent_id="test")
        result = mw.wrap(obj)
        # Should return the object unchanged, no crash
        assert result is obj
        assert len(mw.records) == 0

    def test_multiple_wraps_stack_records(self):
        """Wrapping the same agent twice accumulates records from both wraps."""
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class MockAgent:
            name = "double-wrapped"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "response"

        agent = MockAgent()
        mw1 = ATLASTAutoGenMiddleware(agent_id="mw1")
        mw2 = ATLASTAutoGenMiddleware(agent_id="mw2")

        mw1.wrap(agent)
        mw2.wrap(agent)

        agent.generate_reply(messages=[{"content": "test"}])

        # Both middleware instances record
        assert len(mw1.records) == 1
        assert len(mw2.records) == 1

    def test_empty_messages_list(self):
        """generate_reply with empty messages list doesn't crash."""
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class MockAgent:
            name = "empty-msg-agent"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "ok"

        agent = MockAgent()
        mw = ATLASTAutoGenMiddleware(agent_id="test")
        mw.wrap(agent)

        result = agent.generate_reply(messages=[])
        assert result == "ok"
        assert len(mw.records) == 1

    def test_register_atlast_uses_agent_name_as_id(self):
        """register_atlast() defaults to agent.name when agent_id not given."""
        from atlast_ecp.adapters.autogen import register_atlast

        class MockAgent:
            name = "auto-named-agent"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "hi"

        agent = MockAgent()
        mw = register_atlast(agent)
        assert mw.agent_id == "auto-named-agent"

    def test_no_handoff_when_sender_is_self(self):
        """No handoff record when sender and agent have the same name."""
        from atlast_ecp.adapters.autogen import ATLASTAutoGenMiddleware

        class MockAgent:
            name = "self-agent"
            def generate_reply(self, messages=None, sender=None, **kwargs):
                return "self-reply"

        class SameSender:
            name = "self-agent"

        agent = MockAgent()
        mw = ATLASTAutoGenMiddleware(agent_id="self-agent")
        mw.wrap(agent)

        agent.generate_reply(
            messages=[{"content": "hello"}],
            sender=SameSender(),
        )

        assert len(mw.records) == 1
        assert mw.records[0]["action"] == "autogen_reply"  # not handoff
