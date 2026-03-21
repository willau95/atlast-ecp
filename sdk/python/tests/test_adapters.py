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
