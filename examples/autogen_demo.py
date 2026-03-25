#!/usr/bin/env python3
"""
ATLAST ECP + AutoGen Demo — no API key needed.

Shows how register_atlast() records ECP evidence for AutoGen agent interactions.

Usage:
    pip install atlast-ecp
    python examples/autogen_demo.py
"""

import os, tempfile
from unittest.mock import MagicMock

os.environ["ATLAST_ECP_DIR"] = tempfile.mkdtemp(prefix="atlast_demo_")

from atlast_ecp.adapters.autogen import register_atlast, ATLASTAutoGenMiddleware
from atlast_ecp.storage import load_records

# ─── 1. Single Agent ────────────────────────────────────────────────────────
print("\n=== 1. Single Agent Reply ===")
agent = MagicMock()
agent.name = "assistant"
agent.generate_reply = MagicMock(return_value="The capital of France is Paris.")

middleware = register_atlast(agent, agent_id="demo-assistant")

# Simulate a conversation
result = agent.generate_reply(
    messages=[{"role": "user", "content": "What is the capital of France?"}],
    sender=None,
)
print(f"Agent replied: {result}")
print(f"Records: {len(middleware.records)}")

# ─── 2. Multi-Agent Handoff ─────────────────────────────────────────────────
print("\n=== 2. Multi-Agent Handoff ===")
coder = MagicMock()
coder.name = "coder"
coder.generate_reply = MagicMock(return_value="def hello(): print('hi')")

reviewer = MagicMock()
reviewer.name = "reviewer"
reviewer.generate_reply = MagicMock(return_value="LGTM, code looks clean.")

mw_coder = register_atlast(coder, agent_id="demo-coder")
mw_reviewer = register_atlast(reviewer, agent_id="demo-reviewer")

# Coder generates code
coder.generate_reply(
    messages=[{"role": "user", "content": "Write a hello function"}],
    sender=reviewer,  # reviewer asked coder → handoff detected!
)

# Reviewer reviews
reviewer.generate_reply(
    messages=[{"role": "user", "content": "def hello(): print('hi')"}],
    sender=coder,  # coder sent to reviewer → handoff detected!
)

print(f"Coder records: {len(mw_coder.records)}")
print(f"Reviewer records: {len(mw_reviewer.records)}")

# Check handoff detection
for rec in mw_coder.records:
    if rec.get("meta", {}).get("handoff"):
        print(f"  🔀 Handoff: {rec['meta']['source_agent']} → {rec['meta']['target_agent']}")

for rec in mw_reviewer.records:
    if rec.get("meta", {}).get("handoff"):
        print(f"  🔀 Handoff: {rec['meta']['source_agent']} → {rec['meta']['target_agent']}")

# ─── Summary ────────────────────────────────────────────────────────────────
print(f"\n=== Summary ===")
records = load_records(limit=10)
for r in records:
    print(f"  {r['id']} | {r['action']} | agent={r['agent']}")
print("✅ All agent evidence recorded, handoffs detected")
