# ATLAST ECP Stress Test Experiments

6 agent types × multiple models via OpenRouter. Goal: verify full E2E chain for real-world scenarios.

## Setup
```bash
export OPENROUTER_API_KEY="sk-or-..."
export ATLAST_ECP_DIR=$(mktemp -d)
pip install atlast-ecp[crypto] openai langchain-openai crewai autogen-agentchat
```

## Experiments

| # | Script | Agent Type | Calls | Scenario |
|---|--------|-----------|-------|----------|
| 1 | `01_wrap_coding.py` | OpenClaw wrap | ~40 | Coding agent: multi-step code generation |
| 2 | `02_langchain_research.py` | LangChain | ~30 | Research chain: search → analyze → summarize |
| 3 | `03_track_customer.py` | Native @track | ~150 | Customer service: high-frequency Q&A |
| 4 | `04_crewai_team.py` | CrewAI | ~60 | Team: researcher + writer + reviewer |
| 5 | `05_autogen_debate.py` | AutoGen | ~80 | Multi-agent debate/consensus |
| 6 | `06_chaos_errors.py` | Chaos | ~30 | Error injection, retries, timeouts |

## Run All
```bash
python run_all.py
```

## Expected Output
- `results/` directory with per-experiment ECP records
- `results/summary.json` — aggregate stats
- All records verifiable via `atlast verify`
