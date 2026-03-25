# ATLAST ECP Framework Adapters

One-line integration for popular AI agent frameworks. Each adapter records [ECP evidence](https://github.com/willau95/atlast-ecp) for every LLM call, tool use, and agent interaction — **with zero impact on your agent's behavior**.

## Core Principles

- **Fail-Open**: Adapter errors never crash your agent
- **Privacy-First**: Only SHA-256 hashes stored, raw content never leaves your device
- **Zero Config**: Works with just `pip install atlast-ecp`

---

## LangChain

```python
from atlast_ecp.adapters.langchain import ATLASTCallbackHandler

# Add to any LLM
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o", callbacks=[ATLASTCallbackHandler(agent="my-agent")])

# Or any chain
chain = prompt | llm | parser
chain.invoke({"question": "..."}, config={"callbacks": [ATLASTCallbackHandler()]})

# Or AgentExecutor
agent = AgentExecutor(agent=..., tools=..., callbacks=[ATLASTCallbackHandler()])
```

**Captures**: LLM calls, chat model calls, tool calls, retriever queries, errors.

**Requirements**: `langchain-core >= 0.2.0`

---

## CrewAI

```python
from atlast_ecp.adapters.crewai import ATLASTCrewCallback

# Option 1: Crew-level callback
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    callbacks=[ATLASTCrewCallback(agent="my-crew")],
)

# Option 2: Step-level callback (more granular)
callback = ATLASTCrewCallback(agent="my-crew")
crew = Crew(
    agents=[researcher],
    tasks=[task],
    step_callback=callback.step_callback,
)
```

**Captures**: Task completions, agent steps, tool calls within steps.

**Requirements**: `crewai >= 0.50.0`

---

## AutoGen

```python
from atlast_ecp.adapters.autogen import register_atlast

# One line to register
middleware = register_atlast(my_agent)

# Multi-agent — handoffs are auto-detected
mw_coder = register_atlast(coder)
mw_reviewer = register_atlast(reviewer)
# When coder sends to reviewer, a handoff record is created automatically
```

**Captures**: Agent replies, cross-agent handoffs (with source/target tracking).

**Requirements**: `pyautogen >= 0.2.0` or `autogen-agentchat >= 0.4.0`

---

## Examples

Run the demos (no API key needed):

```bash
python examples/langchain_demo.py
python examples/crewai_demo.py
python examples/autogen_demo.py
```

## Verbose Mode

All adapters support `verbose=True` to print record IDs:

```python
handler = ATLASTCallbackHandler(agent="debug", verbose=True)
# Output: [ATLAST ECP] rec_a1b2c3d4e5f67890
```
