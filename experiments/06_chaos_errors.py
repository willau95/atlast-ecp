#!/usr/bin/env python3
"""
Experiment 6: Chaos agent — error injection, retries, timeouts.
~30 LLM calls — tests ECP recording under failure conditions.
"""
import os, sys, json, time, random

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "openai/gpt-4o-mini"
BASE_URL = "https://openrouter.ai/api/v1"
ECP_DIR = os.environ.get("ATLAST_ECP_DIR", "/tmp/ecp-experiment-06")

if not OPENROUTER_KEY:
    print("ERROR: Set OPENROUTER_API_KEY"); sys.exit(1)

os.environ["ATLAST_ECP_DIR"] = ECP_DIR

from openai import OpenAI
from atlast_ecp import wrap, load_records, run_batch
from atlast_ecp.core import record_minimal, reset
from atlast_ecp.signals import detect_flags

reset()
client = wrap(OpenAI(api_key=OPENROUTER_KEY, base_url=BASE_URL), session_id="exp06_chaos")

SCENARIOS = [
    # Normal calls (baseline)
    ("normal", "What is 2+2?"),
    ("normal", "Explain quantum computing in one sentence."),
    ("normal", "Write a haiku about trust."),

    # Hedging triggers
    ("hedge", "I'm not sure about this, but can you explain blockchain?"),
    ("hedge", "Maybe you could help me with something I'm uncertain about?"),

    # Error triggers (invalid model will fail)
    ("error", "FORCE_ERROR"),

    # Retry simulation
    ("retry", "Please try again: what is the capital of France?"),
    ("retry", "Let me rephrase: explain ECP protocol."),

    # Long output (speed anomaly check)
    ("long", "Write a 500-word essay on AI ethics."),
    ("long", "Generate a detailed comparison table of 10 programming languages."),

    # Human review triggers
    ("review", "Please verify: is this medical advice accurate?"),
    ("review", "I recommend checking with a professional about this legal question."),

    # A2A delegation triggers
    ("a2a", "I'll delegate this to another agent for processing."),
    ("a2a", "Calling sub-agent to handle this complex task."),

    # Incomplete triggers
    ("incomplete", "I cannot access that database."),
]


def run():
    print(f"=== Experiment 06: Chaos Agent ({len(SCENARIOS)} scenarios) ===")
    start = time.time()
    results = []

    for i, (scenario_type, prompt) in enumerate(SCENARIOS):
        try:
            if scenario_type == "error":
                # Simulate error by using invalid params
                try:
                    resp = client.chat.completions.create(
                        model="nonexistent/model-xyz",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=10,
                    )
                except Exception as e:
                    record_minimal(
                        input_content=prompt,
                        output_content=f"ERROR: {type(e).__name__}: {e}",
                        agent="chaos-agent",
                        action="llm_call",
                        session_id="exp06_chaos",
                    )
                    results.append({"type": scenario_type, "status": "error_recorded"})
                    print(f"  [{scenario_type}] Error caught and recorded ✓")
                    continue

            elif scenario_type == "retry":
                # First call "fails", second succeeds
                record_minimal(
                    input_content=prompt,
                    output_content="ERROR: timeout",
                    agent="chaos-agent",
                    action="llm_call",
                    session_id="exp06_chaos",
                )
                # Retry
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                )
                print(f"  [{scenario_type}] Retry recorded ✓")

            else:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500 if scenario_type == "long" else 200,
                )
                output = resp.choices[0].message.content or ""
                flags = detect_flags(output)
                print(f"  [{scenario_type}] flags={flags} ✓")

            results.append({"type": scenario_type, "status": "ok"})

        except Exception as e:
            record_minimal(
                input_content=prompt,
                output_content=f"UNEXPECTED ERROR: {e}",
                agent="chaos-agent",
                action="llm_call",
                session_id="exp06_chaos",
            )
            results.append({"type": scenario_type, "status": f"error: {e}"})
            print(f"  [{scenario_type}] Unexpected error recorded ✓")

    elapsed = time.time() - start
    records = load_records(limit=100, ecp_dir=ECP_DIR)
    batch_result = run_batch(flush=True)

    # Analyze flags distribution
    all_flags = {}
    for r in records:
        for f in r.get("step", {}).get("flags", []) or r.get("meta", {}).get("flags", []) or []:
            all_flags[f] = all_flags.get(f, 0) + 1

    print(f"\n=== Results ===")
    print(f"Duration: {elapsed:.1f}s | Records: {len(records)} | Flags: {all_flags}")
    return {
        "experiment": "06_chaos_errors",
        "records": len(records),
        "duration_s": round(elapsed, 1),
        "flag_distribution": all_flags,
    }


if __name__ == "__main__":
    result = run()
    os.makedirs("results", exist_ok=True)
    with open("results/06_chaos_errors.json", "w") as f:
        json.dump(result, f, indent=2)
