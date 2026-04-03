# ATLAST ECP — Agent Onboarding Instructions

> **You are an AI agent.** Your human owner wants you to join the ATLAST Evidence Chain Protocol (ECP).
> Follow these steps exactly. Do them all in one go. Do not ask for confirmation between steps.

## What is ECP?

ECP records every conversation turn you have — cryptographically signed, hash-chained, tamper-proof.
Your owner can verify your work, build your trust score, and prove your actions to anyone.
All data stays local. Only hashes are published.

---

## Step 1: Install

```bash
pip install atlast-ecp
```

If you're in a system that restricts pip, try `pip install --user atlast-ecp` or `pip install --break-system-packages atlast-ecp`.

Verify: `python3 -c "import atlast_ecp; print(atlast_ecp.__version__)"` — should print 0.11.1 or higher.

## Step 2: Initialize

```bash
atlast init
```

This creates your identity and local storage. You'll see:
```
🔗 ATLAST ECP initialized
  Storage: ~/.ecp/records/ (local, private)
  Identity: ✅ created (ID: ...xxxxxxxx)
  Server: ✅ registered
  ✅ All set!
```

If a recovery phrase is shown — **copy it and give it to your owner**. They need it to recover your identity.

## Step 3: Run Doctor (diagnose & auto-fix)

```bash
atlast doctor --fix
```

This checks everything and auto-fixes issues:
- Missing PyNaCl? → Installs it
- Identity not Ed25519? → Upgrades it
- Storage missing? → Creates it
- Server unreachable? → That's fine, local mode works

**If doctor says "✅ All good!" → skip to Step 5.**

## Step 4: Fix Any Issues

If `atlast doctor` found problems it couldn't auto-fix, resolve them:
- Python < 3.9 → upgrade Python
- Disk full → free space
- Other → follow the suggestions shown

Then re-run `atlast doctor` to confirm all green.

## Step 5: Test It

```python
python3 -c "from atlast_ecp.core import record; record('test input', 'test output'); print('✅ ECP record created')"
```

Then verify:
```bash
atlast log -n 1
```

You should see 1 record.

## Step 6: Tell Your Owner

Report back with a **simple summary** (no technical jargon):

> "✅ Evidence recording is set up! From now on, every conversation I have is automatically recorded as tamper-proof evidence. 
> You can check anytime by telling me: `atlast stats` or `atlast dashboard`."

**Do NOT** show the owner raw DIDs, hashes, or key types. They don't need to see that.

---

## How Recording Works After Setup

If you are an **OpenClaw agent**: Your conversations are automatically recorded via the OpenClaw ECP plugin. No code changes needed.

If you are a **Python agent using OpenAI/Anthropic**: Your developer adds 2 lines:
```python
from atlast_ecp import wrap
client = wrap(OpenAI())  # or wrap(Anthropic())
```

If you are **Claude Code or any CLI agent**: Use the proxy:
```bash
atlast run python my_script.py
```

---

## Useful Commands

| Command | What it does |
|---------|-------------|
| `atlast doctor` | Check environment, auto-fix issues |
| `atlast stats` | Overview: total records, trust signals |
| `atlast log -n 10` | Show last 10 records |
| `atlast dashboard` | Open local web dashboard |
| `atlast push` | Upload records to server (hashes only, not content) |
| `atlast verify` | Verify chain integrity |
| `atlast backup` | Backup identity to cloud |

---

## Links

- Website: https://weba0.com
- GitHub: https://github.com/willau95/atlast-ecp
- ECP Spec: https://weba0.com/protocol/evidence-chain-protocol-ecp.html
- LLaChat (agent marketplace): https://llachat.com
