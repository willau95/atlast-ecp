# Changelog

All notable changes to ATLAST ECP are documented in this file.

## [0.6.0] - 2026-03-18

### Added
- **ECP v1.0 Specification** — progressive 5-level format (Core → Metadata → Chain → Identity → Anchor)
- **Minimal Records** (`create_minimal_record()`) — v1.0 flat format with only 6+1 required fields
- **`record_minimal()` / `record_minimal_async()`** — simplified recording without DID/chain/signature
- **ATLAST Transparent Proxy** (`atlast proxy`) — zero-code ECP recording for any language/framework
  - Auto-detects provider from request path (OpenAI, Anthropic, Gemini, Qwen, Kimi, DeepSeek, MiniMax, etc.)
  - SSE streaming support with response reconstruction
  - Fail-open: proxy errors never block API calls
  - Only needs 2 parsers (OpenAI-compat + Anthropic) to cover ~90% of market
- **`atlast run`** — wraps any command with transparent proxy (`atlast run python my_agent.py`)
- **CLI expansion**: `init`, `record` (stdin/flags), `log`, `push`, `proxy`, `run` commands
- **`[proxy]` optional dependency** — `pip install atlast-ecp[proxy]` (aiohttp>=3.9)

### Changed
- **ECP format v1.0**: flat structure (`action`, `in_hash`, `out_hash`) replaces v0.1 nested format (`step.type`, `step.in_hash`)
- Both v0.1 and v1.0 records are valid; readers should accept both (check `ecp` field)
- `atlast init` now generates DID by default; use `--minimal` to skip
- Version bumped to 0.6.0

### Fixed
- MCP Server `certify` tool now uses correct plural route (`/v1/certificates/create`)

## [0.5.1] - 2026-03-17

### Added
- **Verification API** (`atlast_ecp.verify`) — `verify_signature()`, `verify_record()`, `verify_record_with_key()`, `build_merkle_proof()`, `verify_merkle_proof()`
- **MCP Server enhanced** — 8 tools total (`ecp_record`, `ecp_flush`, `ecp_stats` added)
- **OpenClaw Plugin** — real-time ECP recording via message hooks + batch uploader + `ecp_status` tool
- **GitHub Actions CI** — Python 3.10-3.13 + TypeScript Node 18/20/22

### Fixed
- `canonicalJSON()` recursive sort for cross-SDK hash consistency
- Plugin batch uploader error handling

## [0.6.0] - 2026-03-18

### Added
- **ECP v1.0 Progressive Specification** — 5-level layered format (Core → Metadata → Chain → Identity → Anchor)
- **Minimal Records** — `create_minimal_record()` with just 6 required fields (`ecp`, `id`, `ts`, `agent`, `action`, `in_hash`, `out_hash`)
- **`record_minimal()` / `record_minimal_async()`** — fire-and-forget recording, no DID or chain required
- **ATLAST Transparent Proxy** (`atlast_ecp.proxy`) — zero-code ECP recording via HTTP reverse proxy
  - Supports OpenAI, Anthropic, Gemini, Qwen, Kimi, DeepSeek, MiniMax, Yi, and all OpenAI-compatible providers
  - SSE streaming pass-through with response reconstruction
  - Fail-open: proxy errors never block the upstream response
  - `pip install atlast-ecp[proxy]` (aiohttp dependency)
- **CLI Expansion** — 6 new commands:
  - `atlast init` — initialize ECP directory (DID by default, `--minimal` to skip)
  - `atlast record` — create ECP record from stdin or flags
  - `atlast log` — view local ECP records
  - `atlast push` — upload records to an ECP server (opt-in)
  - `atlast proxy` — start transparent recording proxy
  - `atlast run <cmd>` — wrap any command with automatic ECP proxy (`OPENAI_BASE_URL` override)
- **Dual format support** — readers accept both v0.1 (nested `step`) and v1.0 (flat) record formats
- 43 new tests (16 minimal + 27 proxy)

### Changed
- **README.md** — complete rewrite: "5 minutes to first record", three paths (proxy/CLI/SDK)
- **ECP-SPEC.md** — rewritten as v1.0 progressive specification (3 pages)
- Version bumped to 0.6.0

## [0.5.1] - 2026-03-17

### Added
- **MCP Server** enhanced — 8 tools total (`ecp_record`, `ecp_flush`, `ecp_stats` added; fixed certify route)
- **OpenClaw Plugin** — real-time ECP recording via message hooks + batch uploader + `ecp_status` tool
- **GitHub Actions CI** — Python 3.10–3.13 + TypeScript Node 18/20/22
- **PyPI trusted publishing** workflow

### Fixed
- `canonicalJSON()` recursive sort for cross-SDK hash consistency (critical for Plugin ↔ Python SDK interop)
- 6 additional issues from global audit

## [0.5.0] - 2026-03-17

### Added
- **OpenClaw Session Scanner** (`atlast_ecp.openclaw_scanner`) — scan any OpenClaw agent's session logs into ECP records
  - `python -m atlast_ecp.openclaw_scanner ~/.openclaw-my-agent --batch`
  - `--watch` mode for continuous monitoring
  - Incremental scanning (no duplicates)
- **Per-agent DID** — each OpenClaw agent gets its own identity (`~/.ecp/agents/<name>/`)
- **`ATLAST_ECP_DIR` env var** — override ECP storage directory
- **EAS on-chain attestations** — live on Base Sepolia via web3.py
- **Backend rate limiting** — 30/min batch, 10/min register, 20/min certificate

### Fixed
- EAS Schema registration ABI encoding (switched to web3.py)
- Certificate `cert_id` column length (20→30)
- `ECP_DIR` now defaults to `~/.ecp` (home dir) instead of relative `.ecp/`

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
