# atlast-ecp SDK

Python SDK for the ATLAST Evidence Chain Protocol (ECP).

## Install

```bash
pip install atlast-ecp

# With ed25519 signing (recommended):
pip install atlast-ecp[crypto]
```

## Quick Start

### Option 1 — Python Library Mode (Recommended)

```python
from atlast_ecp import wrap
from anthropic import Anthropic

client = wrap(Anthropic())

# Everything else stays the same
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Analyze this contract."}]
)
```

Also works with OpenAI:

```python
from atlast_ecp import wrap
import openai

client = wrap(openai.OpenAI())
response = client.chat.completions.create(...)
```

### Option 2 — Claude Code Plugin

```bash
npx atlast-ecp install
```

Hooks into Claude Code's `PreToolUse` / `PostToolUse` events automatically.

### Option 3 — OpenClaw Plugin

Tell your agent:
```
See the registration guide in this repository.
```

Or manually: `openclaw plugin add atlast/ecp`

## CLI

```bash
atlast view              # Latest ECP records
atlast verify <id>       # Verify chain integrity
atlast stats             # Trust signals summary
atlast did               # Your agent's DID
atlast flush             # Force Merkle batch upload
```

## Privacy

- Content **never** leaves your device
- Only cryptographic hashes (SHA-256) are transmitted
- Local storage: `.ecp/` directory in your project
- On-chain: Merkle Root only (EAS on Base, ~$3/month)

## Zero Dependencies

Core SDK has zero required dependencies. Runs on any Python 3.10+.

Optional: `pip install cryptography` for ed25519 signing.
