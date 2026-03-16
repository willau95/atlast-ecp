# Changelog

All notable changes to ATLAST ECP are documented in this file.

## [0.4.0] - 2026-03-16

### Added
- **Work Certificates**: `atlast certify <title>` CLI command for issuing verifiable work certificates
- **MCP Tools**: 5 MCP tools — `ecp_stats`, `ecp_verify`, `ecp_records`, `ecp_identity`, `ecp_certify`
- **EAS Preparation**: Live mode ready for Base mainnet (stub mode for dev/testing)

## [0.3.0] - 2026-03-16

### Added
- **OpenTelemetry Auto-Instrumentation**: `from atlast_ecp import init` — 1-line setup
- **ECPSpanExporter**: Converts OTel spans from 11 LLM libraries into ECP records
- **Supported Libraries**: openai, anthropic, google-genai, cohere, mistralai, ollama, transformers, langchain, crewai, llama-index, bedrock
- **Optional dependency**: `pip install atlast-ecp[otel]`
- 14 new OTel tests

## [0.2.1] - 2026-03-16

### Fixed
- **Critical**: `compute_chain_hash()` now zeros both `chain.hash` AND `sig` before hashing (was only zeroing `chain.hash`, causing round-trip verification failure)
- CLI `verify` always checks chain hash (was skipping genesis records)
- `_check_chain_integrity()` uses graph traversal instead of timestamp sorting (fixes same-millisecond edge case)
- CLI `register` uses correct field names (`did`/`public_key`) matching backend schema

## [0.2.0] - 2026-03-16

### Added
- **Google Gemini** wrapper: `wrap(genai.Client())`
- **LiteLLM** wrapper: `wrap(litellm)` — 100+ LLM providers
- `atlast register` CLI command for agent self-registration
- GitHub Actions CI (push/PR, Python 3.10-3.13 matrix)
- PyPI trusted publisher workflow

## [0.1.0] - 2026-03-16

### Added
- Core ECP recording engine (`core.record()`)
- Tamper-proof hash chain with `sha256:` prefixed hashes
- ed25519 cryptographic signing (`[crypto]` extra)
- `wrap()` for Anthropic and OpenAI clients
- Passive behavioral signal detection (6 flags: retried, hedged, incomplete, high_latency, error, human_review)
- Local storage in `.ecp/` directory
- Merkle tree batching with automatic upload
- Agent identity (DID) generation and persistence
- CLI tools: `init`, `view`, `verify`, `stats`, `did`, `flush`, `export`
- MCP server for Claude Desktop / Claude Code
- OpenClaw plugin integration
- Claude Code hooks (PreToolUse/PostToolUse)
- Zero required dependencies
- Fail-open design: recording failures never affect agent operation
- MIT license
