#!/usr/bin/env python3
"""
Experiment 3: Native @track customer service agent.
~150 LLM calls — high-frequency Q&A with tool calls.
"""
import os, sys, json, time, random

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "openai/gpt-4o-mini"  # Fast, cheap for high-frequency
BASE_URL = "https://openrouter.ai/api/v1"
ECP_DIR = os.environ.get("ATLAST_ECP_DIR", "/tmp/ecp-experiment-03")

if not OPENROUTER_KEY:
    print("ERROR: Set OPENROUTER_API_KEY"); sys.exit(1)

os.environ["ATLAST_ECP_DIR"] = ECP_DIR

from openai import OpenAI
from atlast_ecp.core import record, record_minimal, reset
from atlast_ecp import load_records, run_batch

reset()
client = OpenAI(api_key=OPENROUTER_KEY, base_url=BASE_URL)

# Simulated customer questions (high volume)
QUESTIONS = [
    "How do I reset my password?",
    "What's your refund policy?",
    "My order hasn't arrived yet. Order #12345.",
    "Can I change my shipping address?",
    "How do I cancel my subscription?",
    "What payment methods do you accept?",
    "Is there a student discount?",
    "How do I contact a human agent?",
    "My product is defective. What do I do?",
    "Do you ship internationally?",
    "What are your business hours?",
    "How do I track my order?",
    "Can I get an invoice?",
    "How do I update my billing info?",
    "What's the warranty on your products?",
]

TOOLS = [
    {"type": "function", "function": {"name": "lookup_order", "description": "Look up order status", "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {"name": "check_inventory", "description": "Check product availability", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}}},
    {"type": "function", "function": {"name": "create_ticket", "description": "Create support ticket", "parameters": {"type": "object", "properties": {"subject": {"type": "string"}, "priority": {"type": "string"}}, "required": ["subject"]}}},
]


def handle_customer(question: str, session_num: int):
    """Handle one customer interaction (1-3 LLM calls)."""
    messages = [
        {"role": "system", "content": "You are a helpful customer service agent. Be concise and helpful."},
        {"role": "user", "content": question},
    ]

    start = time.time()
    resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS, max_tokens=500)
    latency = int((time.time() - start) * 1000)

    choice = resp.choices[0]
    output = choice.message.content or ""

    # Record via @track style
    record_minimal(
        input_content=question,
        output_content=output,
        agent="customer-service-agent",
        action="llm_call",
        model=MODEL,
        latency_ms=latency,
        session_id=f"exp03_session_{session_num}",
    )

    # If tool call, simulate tool response + follow-up
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            tool_result = json.dumps({"status": "ok", "data": f"Simulated {tc.function.name} result"})
            record_minimal(
                input_content=json.dumps({"tool": tc.function.name, "args": tc.function.arguments}),
                output_content=tool_result,
                agent="customer-service-agent",
                action="tool_call",
                latency_ms=random.randint(10, 50),
                session_id=f"exp03_session_{session_num}",
            )

            # Follow-up LLM call with tool result
            messages.append(choice.message)
            messages.append({"role": "tool", "content": tool_result, "tool_call_id": tc.id})

        start2 = time.time()
        resp2 = client.chat.completions.create(model=MODEL, messages=messages, max_tokens=500)
        latency2 = int((time.time() - start2) * 1000)
        record_minimal(
            input_content=f"Follow-up after {choice.message.tool_calls[0].function.name}",
            output_content=resp2.choices[0].message.content or "",
            agent="customer-service-agent",
            action="llm_call",
            model=MODEL,
            latency_ms=latency2,
            session_id=f"exp03_session_{session_num}",
        )


def run():
    print(f"=== Experiment 03: Customer Service (150 interactions) ===")
    start = time.time()
    total_calls = 0

    for session in range(10):  # 10 "sessions" of 15 questions each
        for q in QUESTIONS:
            try:
                handle_customer(q, session)
                total_calls += 1
                if total_calls % 25 == 0:
                    print(f"  {total_calls} interactions done...")
            except Exception as e:
                record_minimal(
                    input_content=q,
                    output_content=f"ERROR: {e}",
                    agent="customer-service-agent",
                    action="llm_call",
                    session_id=f"exp03_session_{session}",
                )
                total_calls += 1

    elapsed = time.time() - start
    records = load_records(limit=500, ecp_dir=ECP_DIR)
    result = run_batch(flush=True)

    print(f"\n=== Results ===")
    print(f"Duration: {elapsed:.1f}s | Records: {len(records)} | Batch: {result.get('status')}")
    return {"experiment": "03_track_customer", "records": len(records), "duration_s": round(elapsed, 1)}


if __name__ == "__main__":
    result = run()
    os.makedirs("results", exist_ok=True)
    with open("results/03_track_customer.json", "w") as f:
        json.dump(result, f, indent=2)
