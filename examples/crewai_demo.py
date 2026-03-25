#!/usr/bin/env python3
"""
ATLAST ECP + CrewAI Demo — no API key needed.

Shows how ATLASTCrewCallback records ECP evidence for crew task executions.

Usage:
    pip install atlast-ecp
    python examples/crewai_demo.py
"""

import os, tempfile
from unittest.mock import MagicMock

os.environ["ATLAST_ECP_DIR"] = tempfile.mkdtemp(prefix="atlast_demo_")

from atlast_ecp.adapters.crewai import ATLASTCrewCallback
from atlast_ecp.storage import load_records

callback = ATLASTCrewCallback(agent="demo-crew", verbose=True)

# ─── 1. Task Completion Callback ────────────────────────────────────────────
print("\n=== 1. Task Completion ===")
task_output = MagicMock()
task_output.description = "Research the latest AI trends in 2026"
task_output.raw = "Key trends: Agent economies, ECP protocols, trust layers..."
task_output.agent = "researcher"
callback(task_output)

# ─── 2. Another Task with Different Agent ────────────────────────────────────
print("\n=== 2. Writer Task ===")
task_output2 = MagicMock()
task_output2.description = "Write a blog post about AI trust"
task_output2.raw = "# Why AI Agents Need Trust\n\nIn 2026, AI agents..."
task_output2.agent = "writer"
callback(task_output2)

# ─── 3. Step Callback — Tool Call ────────────────────────────────────────────
print("\n=== 3. Step: Tool Call ===")
step = MagicMock()
step.tool = "web_search"
step.tool_input = "ATLAST Protocol 2026"
step.log = "Found 15 results about ATLAST Protocol"
callback.step_callback(step)

# ─── 4. Step Callback — Agent Finish ─────────────────────────────────────────
print("\n=== 4. Step: Agent Finish ===")
finish = MagicMock(spec=["output", "log"])
del finish.tool  # ensure no .tool attr
finish.output = "Task completed successfully"
finish.log = "Agent reasoning: combined search results with domain knowledge"
callback.step_callback(finish)

# ─── 5. Dict-based Output ────────────────────────────────────────────────────
print("\n=== 5. Dict Output ===")
callback({"description": "Summarize findings", "raw": "Summary: 3 key points..."})

# ─── Summary ────────────────────────────────────────────────────────────────
print(f"\n=== Summary ===")
print(f"Records created: {callback.record_count}")
records = load_records(limit=10)
for r in records:
    print(f"  {r['id']} | {r['action']} | agent={r['agent']}")
print("✅ All crew evidence recorded")
