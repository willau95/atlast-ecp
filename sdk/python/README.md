# atlast-ecp

Python SDK for the **ATLAST Evidence Chain Protocol (ECP)** — trust infrastructure for AI agents.

[![PyPI](https://img.shields.io/pypi/v/atlast-ecp)](https://pypi.org/project/atlast-ecp/)
[![Tests](https://img.shields.io/badge/tests-440%20passing-brightgreen)]()
[![Python](https://img.shields.io/pypi/pyversions/atlast-ecp)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

## Install

```bash
pip install atlast-ecp

# With ed25519 signing:
pip install atlast-ecp[crypto]

# With transparent proxy (Layer 0):
pip install atlast-ecp[proxy]
```

## Three Integration Layers

### Layer 0 — Zero Code (transparent proxy)

```bash
atlast run python my_agent.py
# or: OPENAI_BASE_URL=http://localhost:8340 python my_agent.py
```

### Layer 1 — One Line (`wrap`)

```python
from atlast_ecp import wrap
from openai import OpenAI

client = wrap(OpenAI())  # Records every LLM call automatically
response = client.chat.completions.create(model="gpt-4o", messages=[...])
```

Works with: **OpenAI, Anthropic, Google Gemini, LiteLLM**.

### Layer 2 — Framework Adapters

```python
# LangChain
from atlast_ecp.adapters.langchain import ATLASTCallbackHandler
llm = ChatOpenAI(callbacks=[ATLASTCallbackHandler(agent="my-agent")])

# CrewAI
from atlast_ecp.adapters.crewai import ATLASTCrewCallback
crew = Crew(callbacks=[ATLASTCrewCallback(agent="my-crew")])

# AutoGen
from atlast_ecp.adapters.autogen import register_atlast
register_atlast(my_agent)
```

## CLI

```bash
atlast init              # Initialize ~/.ecp/
atlast record            # Create ECP record
atlast log               # View latest records
atlast verify <id>       # Verify chain integrity
atlast stats             # Trust signals
atlast insights          # Performance analytics
atlast proxy             # Start transparent proxy
atlast run <cmd>         # Run with auto-proxy
atlast did               # Agent DID
```

## Module Stability

| Module | Status | Description |
|--------|--------|-------------|
| `core` | 🟢 **Stable** | `record_minimal()`, `record()` |
| `wrap` | 🟢 **Stable** | `wrap(client)` for OpenAI/Anthropic/Gemini |
| `record` | 🟢 **Stable** | ECP record creation (v1.0 spec) |
| `batch` | 🟢 **Stable** | Merkle tree + batch upload |
| `verify` | 🟢 **Stable** | Signature + Merkle proof verification |
| `storage` | 🟢 **Stable** | Local ~/.ecp/ file storage |
| `signals` | 🟢 **Stable** | Trust signal computation |
| `identity` | 🟢 **Stable** | DID + Ed25519 key management |
| `config` | 🟢 **Stable** | Environment/config management |
| `insights` | 🟢 **Stable** | Performance analytics |
| `webhook` | 🟢 **Stable** | HMAC-signed webhook delivery |
| `adapters.*` | 🟢 **Stable** | LangChain, CrewAI, AutoGen |
| `proxy` | 🟡 **Beta** | Transparent HTTP proxy (Layer 0) |
| `a2a` | 🟡 **Beta** | Agent-to-Agent handoff tracking |
| `cli` | 🟡 **Beta** | `atlast` CLI |
| `mcp_server` | 🟠 **Experimental** | MCP tools server |
| `otel_exporter` | 🟠 **Experimental** | OpenTelemetry exporter |
| `openclaw_scanner` | 🟠 **Experimental** | OpenClaw session log scanner |
| `auto` | 🟠 **Experimental** | OTel auto-instrumentation |

## Privacy

- Content **never** leaves your device — only SHA-256 hashes transmitted
- Local storage: `~/.ecp/records/`
- On-chain: Merkle root only (EAS on Base)
- **Fail-Open**: SDK errors never crash your agent

## Links

- [GitHub](https://github.com/willau95/atlast-ecp)
- [Architecture](https://github.com/willau95/atlast-ecp/blob/main/ARCHITECTURE.md)
- [Changelog](https://github.com/willau95/atlast-ecp/blob/main/CHANGELOG.md)
- [ECP Spec](https://github.com/willau95/atlast-ecp/blob/main/docs/ECP-SPEC.md)
