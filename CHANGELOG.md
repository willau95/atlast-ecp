# Changelog

All notable changes to the ATLAST ECP SDK and Server.

## [0.8.0] — 2026-03-21 (Phase 5)

### Added
- Framework adapter examples (`examples/langchain_demo.py`, `crewai_demo.py`, `autogen_demo.py`)
- Adapter integration README (`sdk/python/atlast_ecp/adapters/README.md`)
- 21 edge-case adapter tests (total: 50 adapter tests)
- 34 proxy unit tests (`tests/test_proxy.py`)

### Changed
- Monorepo restructure: `atlast-ecp-server` merged into `server/`, SDKs reorganized to `sdk/{python,typescript,go}/`

## [0.7.0] — 2026-03-20

### Added
- **Insights Layer B**: Performance analytics, trend detection, tool usage analysis (`insights.py`)
- **AutoGen adapter**: `register_atlast()` one-liner, handoff detection (`adapters/autogen.py`)
- **Webhook module**: HMAC-SHA256 signed webhook delivery (`webhook.py`)
- **Discovery module**: `.well-known/ecp.json` service discovery
- **A2A handoff records**: Cross-agent message tracking with `batch_id` drill-down
- `in_hash`/`out_hash` fields in batch upload payload
- Certificate schema documentation (`CERTIFICATE-SCHEMA.md`)

### Fixed
- Insights `_get_meta()` extracts latency from v0.1 execution array
- `urllib` imports moved to module level for CI mock patching
- `ATLAST_API_URL` set in test conftest for CI
- 9 production bugs found via real-world scenario testing
- Safe identity migration preserving DID for registered agents

## [0.6.0] — 2026-03-18

### Added
- **ECP-SPEC v1.0**: Progressive 5-level record specification
- **ATLAST Proxy** (`proxy.py`): Transparent HTTP reverse proxy for zero-code ECP recording
- **`create_minimal_record()`**: Lightweight v1.0 6-field records
- **CLI expansion**: `atlast init`, `atlast record`, `atlast log`, `atlast push`, `atlast proxy`, `atlast run`
- 243 tests passing

### Changed
- Architecture shift: ECP is now **protocol+CLI first, SDK second**
- Local-first default, publishing opt-in

## [0.5.1] — 2026-03-17

### Added
- **Verification module** (`verify.py`): `verify_signature()`, `build_merkle_proof()`, `verify_merkle_proof()`, `verify_record()`
- GitHub Actions CI (`ci.yml`) — Python multi-version + TypeScript
- PyPI trusted publishing workflow

### Fixed
- Critical: `compute_chain_hash` must zero `sig` field before hashing
- CLI verify always checks chain hash
- Chain integrity uses graph traversal

## [0.5.0] — 2026-03-16

### Added
- **Core SDK**: `record()`, `wrap(client)`, identity/DID, storage, batch/Merkle, signals
- **Adapters**: LangChain callback handler, CrewAI callback
- **CLI**: `atlast register`, `atlast verify`, `atlast flush`
- **MCP Server**: Query ECP records via Model Context Protocol
- **OpenClaw scanner**: Scan OpenClaw session logs for ECP records
- 181 tests passing, published on PyPI

## [0.2.0] — 2026-03-16

### Added
- Gemini + LiteLLM `wrap()` support
- `atlast register` CLI command

### Fixed
- Align CLI register payload with backend schema (did, public_key)

## [0.1.0] — 2026-03-15

### Added
- Initial ECP SDK: Library Mode + Claude Code Plugin + OpenClaw Plugin
- ECP-SPEC v0.1
- FastAPI reference backend (23 tests)
- 85 tests passing
