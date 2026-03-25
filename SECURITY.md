# Security Policy

## Scope

This policy covers:
- **ATLAST ECP Python SDK** (`atlast-ecp` on PyPI)
- **ATLAST ECP TypeScript SDK** (`atlast-ecp-ts` on npm)
- **ECP Reference Server** (`server/`)
- **ECP Proxy** (`atlast proxy` / `atlast run`)

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email: **security@atlast.dev** (or open a private security advisory on GitHub)

Include:
1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to release a fix within 7 days for critical issues.

## Security Design Principles

ECP is built with security as a core principle:

- **Privacy by design**: Only SHA-256 hashes leave the device. Raw content is never transmitted.
- **Fail-Open**: SDK/recording failures never crash the host agent.
- **API keys are hashed**: The Reference Server stores only SHA-256 hashes of API keys, never plaintext.
- **Merkle verification**: Batch integrity is cryptographically verified on upload.
- **Ed25519 signatures**: Optional record signing uses Ed25519 (Level 4+).

## Known Limitations

- The Reference Server uses SQLite, which is not designed for high-concurrency production use. For production deployments, consider PostgreSQL.
- API key rotation is not yet implemented in the Reference Server.
- Rate limiting is not built into the Reference Server (use a reverse proxy like nginx).
