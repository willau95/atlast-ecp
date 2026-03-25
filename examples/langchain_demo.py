#!/usr/bin/env python3
"""
ATLAST ECP + LangChain Demo — no API key needed.

Shows how ATLASTCallbackHandler records ECP evidence for LLM/tool calls.

Usage:
    pip install atlast-ecp langchain-core
    python examples/langchain_demo.py
"""

import os, tempfile
from uuid import uuid4
from unittest.mock import MagicMock

# Point ECP storage to a temp dir so we don't pollute ~/.ecp
os.environ["ATLAST_ECP_DIR"] = tempfile.mkdtemp(prefix="atlast_demo_")

from atlast_ecp.adapters.langchain import ATLASTCallbackHandler
from atlast_ecp.storage import load_records

handler = ATLASTCallbackHandler(agent="demo-langchain", verbose=True)

# ─── 1. Simulate an LLM Call ────────────────────────────────────────────────
print("\n=== 1. LLM Call ===")
run_id = uuid4()
handler.on_llm_start(
    serialized={"kwargs": {"model_name": "gpt-4o"}},
    prompts=["Explain quantum computing in one sentence."],
    run_id=run_id,
)

mock_response = MagicMock()
mock_gen = MagicMock()
mock_gen.text = "Quantum computing uses qubits that can be 0 and 1 simultaneously."
mock_response.generations = [[mock_gen]]
mock_response.llm_output = {"token_usage": {"prompt_tokens": 12, "completion_tokens": 15}}
handler.on_llm_end(response=mock_response, run_id=run_id)

# ─── 2. Simulate a Chat Model Call ──────────────────────────────────────────
print("\n=== 2. Chat Model Call ===")
run_id2 = uuid4()
mock_msg = MagicMock()
mock_msg.type = "human"
mock_msg.content = "What is 2+2?"
handler.on_chat_model_start(
    serialized={"kwargs": {"model": "claude-sonnet-4-20250514"}},
    messages=[[mock_msg]],
    run_id=run_id2,
)

mock_resp2 = MagicMock()
mock_gen2 = MagicMock()
mock_gen2.text = ""
mock_gen2.message = MagicMock(content="The answer is 4.")
mock_resp2.generations = [[mock_gen2]]
mock_resp2.llm_output = None
handler.on_llm_end(response=mock_resp2, run_id=run_id2)

# ─── 3. Simulate a Tool Call ────────────────────────────────────────────────
print("\n=== 3. Tool Call ===")
run_id3 = uuid4()
handler.on_tool_start(
    serialized={"name": "calculator"},
    input_str="2 + 2",
    run_id=run_id3,
)
handler.on_tool_end(output="4", run_id=run_id3)

# ─── 4. Simulate an Error ───────────────────────────────────────────────────
print("\n=== 4. Error (Fail-Open) ===")
run_id4 = uuid4()
handler.on_llm_start(
    serialized={"kwargs": {"model_name": "gpt-4o"}},
    prompts=["This will fail"],
    run_id=run_id4,
)
handler.on_llm_error(error=RuntimeError("Rate limit exceeded"), run_id=run_id4)

# ─── Summary ────────────────────────────────────────────────────────────────
print(f"\n=== Summary ===")
print(f"Records created: {handler.record_count}")
records = load_records(limit=10)
for r in records:
    print(f"  {r['id']} | {r['action']} | agent={r['agent']}")

print(f"\nECP data stored in: {os.environ['ATLAST_ECP_DIR']}")
print("✅ All ECP evidence recorded locally (only SHA-256 hashes, no raw content)")
