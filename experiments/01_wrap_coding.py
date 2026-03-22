#!/usr/bin/env python3
"""
Experiment 1: OpenClaw-style wrap() coding agent.
~40 LLM calls — multi-step code generation with iteration.

Uses OpenRouter API (OpenAI-compatible).
"""
import os
import sys
import json
import time

# --- Config ---
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "anthropic/claude-3.5-haiku"  # Mid-tier, not cheapest
BASE_URL = "https://openrouter.ai/api/v1"
ECP_DIR = os.environ.get("ATLAST_ECP_DIR", "/tmp/ecp-experiment-01")

if not OPENROUTER_KEY:
    print("ERROR: Set OPENROUTER_API_KEY"); sys.exit(1)

os.environ["ATLAST_ECP_DIR"] = ECP_DIR

from openai import OpenAI
from atlast_ecp import wrap, load_records, run_batch

client = wrap(OpenAI(api_key=OPENROUTER_KEY, base_url=BASE_URL), session_id="exp01_coding")

# --- Scenario: Build a Python CLI tool step by step ---
TASKS = [
    "Design a Python CLI tool for converting CSV to JSON. Give me the architecture (modules, functions).",
    "Write the main.py with argparse and file I/O.",
    "Write csv_parser.py that handles edge cases (quoted commas, newlines in fields).",
    "Write json_writer.py with pretty-print and compact modes.",
    "Write unit tests for csv_parser.py (at least 5 test cases).",
    "Write unit tests for json_writer.py.",
    "Review all the code above. Find bugs and suggest fixes.",
    "Apply the bug fixes and show the final version of each file.",
    "Write a README.md for this tool.",
    "Generate a pyproject.toml for publishing to PyPI.",
]

# Each task also has follow-up refinements (~3 calls per task = ~40 total)
REFINEMENTS = [
    "Make it more robust.",
    "Add error handling for edge cases.",
    "Optimize for large files (streaming).",
]

def run():
    print(f"=== Experiment 01: Coding Agent ({len(TASKS)} tasks + refinements) ===")
    start = time.time()
    conversation = []

    for i, task in enumerate(TASKS):
        conversation.append({"role": "user", "content": task})
        resp = client.chat.completions.create(
            model=MODEL,
            messages=conversation,
            max_tokens=2000,
        )
        answer = resp.choices[0].message.content
        conversation.append({"role": "assistant", "content": answer})
        print(f"  Task {i+1}/{len(TASKS)}: {task[:50]}... ✓")

        # Add 1 refinement every 3 tasks
        if i % 3 == 2 and i < len(TASKS) - 1:
            ref = REFINEMENTS[i // 3 % len(REFINEMENTS)]
            conversation.append({"role": "user", "content": ref})
            resp2 = client.chat.completions.create(
                model=MODEL,
                messages=conversation,
                max_tokens=1500,
            )
            conversation.append({"role": "assistant", "content": resp2.choices[0].message.content})
            print(f"    Refinement: {ref[:40]}... ✓")

    elapsed = time.time() - start
    records = load_records(limit=100, ecp_dir=ECP_DIR)

    # Trigger batch upload
    result = run_batch(flush=True)

    print(f"\n=== Results ===")
    print(f"Duration: {elapsed:.1f}s")
    print(f"ECP records: {len(records)}")
    print(f"Batch: {result}")
    return {"experiment": "01_wrap_coding", "records": len(records), "duration_s": round(elapsed, 1)}


if __name__ == "__main__":
    result = run()
    os.makedirs("results", exist_ok=True)
    with open("results/01_wrap_coding.json", "w") as f:
        json.dump(result, f, indent=2)
