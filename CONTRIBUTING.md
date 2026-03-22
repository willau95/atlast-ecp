# Contributing to ATLAST ECP

Thank you for your interest in contributing to the Evidence Chain Protocol!

## Development Setup

### Monorepo Structure

```
atlast-ecp/
├── sdk/python/       # Python SDK (PyPI: atlast-ecp)
├── sdk/typescript/   # TypeScript SDK (npm: @atlast/sdk)
├── sdk/go/           # Go SDK (placeholder)
├── server/           # ECP Reference Server (FastAPI)
├── whitepaper/       # Whitepaper + Litepaper (EN + ZH)
├── docs/             # ADRs, migration guides, specs
├── ECP-SPEC.md       # Protocol specification
└── INTERFACE-CONTRACT.md  # Atlas ↔ LLaChat contract
```

### Python SDK

```bash
git clone https://github.com/willau95/atlast-ecp.git
cd atlast-ecp/sdk/python
pip install -e ".[dev,proxy,adapters]"
pytest -v
```

### TypeScript SDK

```bash
cd sdk/typescript
npm install
npm test
```

### Reference Server

```bash
cd server
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Making Changes

1. **Fork** the repo and create a branch from `main`
2. **Write tests** for any new functionality
3. **Run the full test suite** before submitting:
   ```bash
   cd sdk/python && pytest -v              # Python SDK (506+ tests)
   cd sdk/typescript && npm test           # TypeScript SDK (39+ tests)
   cd server && python -m pytest tests/ -v # Reference Server (42+ tests)
   ```
4. **Update documentation** if you changed public APIs
5. **Update CHANGELOG.md** for user-facing changes

## Code Conventions

- **Python**: Type hints everywhere. `from __future__ import annotations`.
- **TypeScript**: Strict mode. No `any` unless absolutely necessary.
- **Tests**: Descriptive names (`test_upload_batch_wrong_key`, not `test_3`).
- **Fail-Open**: Recording/SDK failures must NEVER crash the host agent.
- **Privacy**: Never log or transmit raw content. Hashes only.

## ECP Spec Compliance

All contributions must maintain compatibility with [ECP-SPEC.md](ECP-SPEC.md):

- Accept both v0.1 (nested) and v1.0 (flat) record formats
- `hash_content()` output must be identical across Python, TypeScript, and Go SDKs
- Record IDs: `rec_` + 16 hex characters
- Merkle root algorithm: sort → pair → SHA-256 (see `verify.py`)

## Cross-SDK Hash Consistency

If you modify `hash_content()` or Merkle tree logic in any SDK, you **must** verify the output matches all other SDKs. This is a protocol invariant.

```python
# This must produce the same hash in Python, TypeScript, and Go:
hash_content("hello") == "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
```

## Adapter Guidelines

Framework adapters (LangChain, CrewAI, etc.) must:

- Have **zero required dependencies** on the framework
- Import the framework at runtime only
- Degrade gracefully (no-op) if the framework is not installed
- Include tests that work without the framework installed

## Reporting Security Issues

See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
