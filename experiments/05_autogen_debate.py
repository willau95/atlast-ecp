#!/usr/bin/env python3
"""
Experiment 5: AutoGen-style multi-agent debate.
~80 LLM calls — 4 agents debate, reach consensus.
"""
import os, sys, json, time

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "anthropic/claude-3.5-haiku"
BASE_URL = "https://openrouter.ai/api/v1"
ECP_DIR = os.environ.get("ATLAST_ECP_DIR", "/tmp/ecp-experiment-05")

if not OPENROUTER_KEY:
    print("ERROR: Set OPENROUTER_API_KEY"); sys.exit(1)

os.environ["ATLAST_ECP_DIR"] = ECP_DIR

from openai import OpenAI
from atlast_ecp.core import record_minimal, reset
from atlast_ecp import load_records, run_batch

reset()
client = OpenAI(api_key=OPENROUTER_KEY, base_url=BASE_URL)

DEBATERS = {
    "optimist": "You believe AI agents will be net positive. Argue for trust and autonomy.",
    "skeptic": "You believe AI agents pose serious risks. Argue for strict regulation.",
    "pragmatist": "You seek balanced solutions. Find middle ground between positions.",
    "judge": "You evaluate arguments. Determine which points are strongest and reach a verdict.",
}

DEBATE_TOPICS = [
    "Should AI agents be allowed to make financial transactions autonomously?",
    "Is cryptographic evidence sufficient for AI accountability?",
    "Should there be a global registry of AI agent identities?",
    "Can trust scores replace human oversight?",
]


def debate_round(topic: str, topic_num: int):
    """Run a 5-round debate on a topic with 4 agents."""
    session = f"exp05_debate_{topic_num}"
    history = []

    for round_num in range(5):
        for agent_name, system_prompt in DEBATERS.items():
            context = f"Topic: {topic}\n\nPrevious arguments:\n" + "\n".join(history[-6:]) if history else f"Topic: {topic}"
            prompt = f"{context}\n\nRound {round_num+1}: Present your argument in 2-3 sentences."
            if agent_name == "judge" and round_num == 4:
                prompt = f"{context}\n\nFinal round. Deliver your verdict: which position is strongest and why?"

            start = time.time()
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
            )
            latency = int((time.time() - start) * 1000)
            content = resp.choices[0].message.content or ""
            history.append(f"[{agent_name}] {content}")

            record_minimal(
                input_content=prompt[:500],
                output_content=content,
                agent=f"debate/{agent_name}",
                action="llm_call",
                model=MODEL,
                latency_ms=latency,
                session_id=session,
                delegation_id=f"debate_{topic_num}_round_{round_num}",
                delegation_depth=1,
            )

    # Orchestrator record
    record_minimal(
        input_content=topic,
        output_content=f"Debate completed: {len(DEBATERS)} agents × 5 rounds = 20 calls",
        agent="debate/orchestrator",
        action="a2a_call",
        session_id=session,
        delegation_depth=0,
    )


def run():
    print(f"=== Experiment 05: AutoGen Debate ({len(DEBATE_TOPICS)} topics × 4 agents × 5 rounds) ===")
    start = time.time()

    for i, topic in enumerate(DEBATE_TOPICS):
        debate_round(topic, i)
        print(f"  Debate {i+1}/{len(DEBATE_TOPICS)}: {topic[:50]}... ✓")

    elapsed = time.time() - start
    records = load_records(limit=200, ecp_dir=ECP_DIR)
    result = run_batch(flush=True)

    print(f"\n=== Results ===")
    print(f"Duration: {elapsed:.1f}s | Records: {len(records)} | Batch: {result.get('status')}")
    return {"experiment": "05_autogen_debate", "records": len(records), "duration_s": round(elapsed, 1)}


if __name__ == "__main__":
    result = run()
    os.makedirs("results", exist_ok=True)
    with open("results/05_autogen_debate.json", "w") as f:
        json.dump(result, f, indent=2)
