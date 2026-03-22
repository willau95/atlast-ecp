#!/usr/bin/env python3
"""
Experiment 2: LangChain research chain.
~30 LLM calls — search → analyze → summarize pipeline.
"""
import os, sys, json, time

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "anthropic/claude-3.5-haiku"
BASE_URL = "https://openrouter.ai/api/v1"
ECP_DIR = os.environ.get("ATLAST_ECP_DIR", "/tmp/ecp-experiment-02")

if not OPENROUTER_KEY:
    print("ERROR: Set OPENROUTER_API_KEY"); sys.exit(1)

os.environ["ATLAST_ECP_DIR"] = ECP_DIR

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from atlast_ecp.adapters.langchain import ATLASTCallbackHandler
from atlast_ecp import load_records, run_batch

handler = ATLASTCallbackHandler(agent="research-agent", verbose=True, session_id="exp02_research")
llm = ChatOpenAI(
    model=MODEL,
    api_key=OPENROUTER_KEY,
    base_url=BASE_URL,
    callbacks=[handler],
    max_tokens=1500,
)
parser = StrOutputParser()

TOPICS = [
    "Impact of EU AI Act on autonomous AI agents in financial services",
    "Comparison of agent trust frameworks: ATLAST vs NIST AI RMF vs ISO 42001",
    "How blockchain-based attestation enables agent accountability",
    "Multi-agent delegation patterns and their trust implications",
    "Cost analysis of on-chain vs off-chain evidence anchoring",
]

def run():
    print(f"=== Experiment 02: LangChain Research ({len(TOPICS)} topics × 3 stages) ===")
    start = time.time()

    for i, topic in enumerate(TOPICS):
        # Stage 1: Research outline
        outline_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a research analyst. Create a detailed outline."),
            ("user", "Research topic: {topic}\n\nCreate a 5-section outline with key questions for each.")
        ])
        chain1 = outline_prompt | llm | parser
        outline = chain1.invoke({"topic": topic})
        print(f"  Topic {i+1} outline ✓")

        # Stage 2: Deep analysis
        analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a senior analyst. Provide deep analysis based on this outline."),
            ("user", "Outline:\n{outline}\n\nProvide detailed analysis for each section with evidence and examples.")
        ])
        chain2 = analysis_prompt | llm | parser
        analysis = chain2.invoke({"outline": outline})
        print(f"  Topic {i+1} analysis ✓")

        # Stage 3: Executive summary
        summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an executive writer. Summarize for C-suite."),
            ("user", "Analysis:\n{analysis}\n\nWrite a 200-word executive summary with 3 key takeaways.")
        ])
        chain3 = summary_prompt | llm | parser
        summary = chain3.invoke({"analysis": analysis})
        print(f"  Topic {i+1} summary ✓")

        # Stage 4: Critique
        critique_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a devil's advocate. Challenge the analysis."),
            ("user", "Summary:\n{summary}\n\nIdentify 3 weaknesses or counterarguments.")
        ])
        chain4 = critique_prompt | llm | parser
        chain4.invoke({"summary": summary})
        print(f"  Topic {i+1} critique ✓")

        # Stage 5: Final revised summary
        final_prompt = ChatPromptTemplate.from_messages([
            ("system", "Revise the summary addressing the critique."),
            ("user", "Original summary:\n{summary}\n\nRevise to address weaknesses.")
        ])
        chain5 = final_prompt | llm | parser
        chain5.invoke({"summary": summary})
        print(f"  Topic {i+1} final ✓")

    elapsed = time.time() - start
    records = load_records(limit=200, ecp_dir=ECP_DIR)
    result = run_batch(flush=True)

    print(f"\n=== Results ===")
    print(f"Duration: {elapsed:.1f}s | Records: {handler.record_count} | Batch: {result.get('status')}")
    return {"experiment": "02_langchain_research", "records": handler.record_count, "duration_s": round(elapsed, 1)}


if __name__ == "__main__":
    result = run()
    os.makedirs("results", exist_ok=True)
    with open("results/02_langchain_research.json", "w") as f:
        json.dump(result, f, indent=2)
