# ATLAST ECP Examples

Runnable demos — **no API key needed** (all use mocks).

## Quick Start

```bash
pip install atlast-ecp langchain-core
python examples/langchain_demo.py
python examples/crewai_demo.py
python examples/autogen_demo.py
```

## Examples

| File | Framework | What it shows |
|------|-----------|--------------|
| `langchain_demo.py` | LangChain | LLM calls, chat model, tool calls, error handling |
| `crewai_demo.py` | CrewAI | Task callbacks, step callbacks, multi-agent crews |
| `autogen_demo.py` | AutoGen | Single agent, multi-agent handoff detection |

## What Happens

Each demo:
1. Creates mock LLM interactions (no real API calls)
2. Records ECP evidence via the adapter
3. Prints record IDs and a summary
4. Stores data in a temp directory (auto-cleaned)

All records contain only SHA-256 hashes — no raw content is stored.
