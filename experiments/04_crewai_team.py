#!/usr/bin/env python3
"""
Experiment 4: CrewAI team simulation.
~60 LLM calls — researcher + writer + reviewer pipeline.

Note: CrewAI may not be installed. This script simulates the pattern
using direct OpenAI calls with ATLASTCrewCallback.
"""
import os, sys, json, time

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "anthropic/claude-3.5-haiku"
BASE_URL = "https://openrouter.ai/api/v1"
ECP_DIR = os.environ.get("ATLAST_ECP_DIR", "/tmp/ecp-experiment-04")

if not OPENROUTER_KEY:
    print("ERROR: Set OPENROUTER_API_KEY"); sys.exit(1)

os.environ["ATLAST_ECP_DIR"] = ECP_DIR

from openai import OpenAI
from atlast_ecp.core import record_minimal, reset
from atlast_ecp import load_records, run_batch

reset()
client = OpenAI(api_key=OPENROUTER_KEY, base_url=BASE_URL)

PROJECTS = [
    "Write a technical blog post about zero-knowledge proofs for non-technical readers",
    "Create a competitive analysis of AI agent frameworks (LangChain vs CrewAI vs AutoGen)",
    "Draft a proposal for implementing ECP in enterprise environments",
    "Write a tutorial on building a multi-agent system with trust verification",
]

AGENTS = {
    "researcher": "You are a thorough researcher. Find key facts, cite sources, identify gaps.",
    "writer": "You are an expert technical writer. Make complex topics accessible.",
    "reviewer": "You are a strict editor. Find errors, improve clarity, ensure accuracy.",
}


def crew_pipeline(project: str, project_num: int):
    """Simulate a 3-agent crew working on a project."""
    session = f"exp04_project_{project_num}"

    # Step 1: Researcher gathers info (3 calls)
    research_messages = [
        {"role": "system", "content": AGENTS["researcher"]},
        {"role": "user", "content": f"Research this topic thoroughly: {project}"}
    ]
    for step in range(3):
        start = time.time()
        resp = client.chat.completions.create(model=MODEL, messages=research_messages, max_tokens=1500)
        latency = int((time.time() - start) * 1000)
        content = resp.choices[0].message.content
        record_minimal(
            input_content=research_messages[-1]["content"],
            output_content=content,
            agent="crew/researcher",
            action="llm_call",
            model=MODEL,
            latency_ms=latency,
            session_id=session,
            delegation_depth=1,
        )
        research_messages.append({"role": "assistant", "content": content})
        if step < 2:
            follow_up = ["Now go deeper on the most important point.", "Identify 3 counterarguments."][step]
            research_messages.append({"role": "user", "content": follow_up})

    research_output = content

    # Step 2: Writer creates draft (3 calls)
    writer_messages = [
        {"role": "system", "content": AGENTS["writer"]},
        {"role": "user", "content": f"Based on this research, write a draft:\n\n{research_output}"}
    ]
    for step in range(3):
        start = time.time()
        resp = client.chat.completions.create(model=MODEL, messages=writer_messages, max_tokens=2000)
        latency = int((time.time() - start) * 1000)
        content = resp.choices[0].message.content
        record_minimal(
            input_content=writer_messages[-1]["content"][:500],
            output_content=content,
            agent="crew/writer",
            action="llm_call",
            model=MODEL,
            latency_ms=latency,
            session_id=session,
            delegation_depth=1,
        )
        writer_messages.append({"role": "assistant", "content": content})
        if step < 2:
            follow_up = ["Improve the introduction hook.", "Add a practical example."][step]
            writer_messages.append({"role": "user", "content": follow_up})

    draft = content

    # Step 3: Reviewer provides feedback (3 calls)
    reviewer_messages = [
        {"role": "system", "content": AGENTS["reviewer"]},
        {"role": "user", "content": f"Review this draft critically:\n\n{draft}"}
    ]
    for step in range(3):
        start = time.time()
        resp = client.chat.completions.create(model=MODEL, messages=reviewer_messages, max_tokens=1500)
        latency = int((time.time() - start) * 1000)
        content = resp.choices[0].message.content
        record_minimal(
            input_content=reviewer_messages[-1]["content"][:500],
            output_content=content,
            agent="crew/reviewer",
            action="llm_call",
            model=MODEL,
            latency_ms=latency,
            session_id=session,
            delegation_depth=1,
        )
        reviewer_messages.append({"role": "assistant", "content": content})
        if step < 2:
            follow_up = ["Focus on factual accuracy.", "Suggest structural improvements."][step]
            reviewer_messages.append({"role": "user", "content": follow_up})

    # Step 4: A2A delegation record (parent orchestrator)
    record_minimal(
        input_content=project,
        output_content=f"Crew completed: 3 agents × 3 steps = 9 LLM calls",
        agent="crew/orchestrator",
        action="a2a_call",
        session_id=session,
        delegation_depth=0,
    )


def run():
    print(f"=== Experiment 04: CrewAI Team ({len(PROJECTS)} projects × 3 agents × 3 steps) ===")
    start = time.time()

    for i, project in enumerate(PROJECTS):
        crew_pipeline(project, i)
        print(f"  Project {i+1}/{len(PROJECTS)}: {project[:50]}... ✓")

    elapsed = time.time() - start
    records = load_records(limit=200, ecp_dir=ECP_DIR)
    result = run_batch(flush=True)

    print(f"\n=== Results ===")
    print(f"Duration: {elapsed:.1f}s | Records: {len(records)} | Batch: {result.get('status')}")
    return {"experiment": "04_crewai_team", "records": len(records), "duration_s": round(elapsed, 1)}


if __name__ == "__main__":
    result = run()
    os.makedirs("results", exist_ok=True)
    with open("results/04_crewai_team.json", "w") as f:
        json.dump(result, f, indent=2)
