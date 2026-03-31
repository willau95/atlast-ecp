# Changelog

All notable changes to the ATLAST ECP SDK and Server.

## [Unreleased]

### Added
- **Spec §9 Session-Level Aggregation**: optional `session_summary` record type for aggregating per-action behavioral flags into cacheable session-level metrics (`delivery_score`, `calibration_flag_rate`) and chaining summaries via `prev_session` for cross-session drift detection. Closes #3.

---

## [0.10.0-post] — 2026-03-25 (Post-release Fixes)

### Fixed
- **CI: Smoke test discovery** — use `.eas.schema_uid` path to match actual JSON structure
- **CI: Smoke test health** — accept `ok` status from production health endpoint
- **CI: Server tests** — add `aiosqlite` to server requirements, fixes 17 test errors

### Published
- **npm**: `atlast-ecp-ts@0.3.0` published to registry
- **GitHub Release v0.10.0**: updated with PyPI + npm package links

### Upgraded
- Local dev: `pip install atlast-ecp` → 0.10.0 (was 0.8.1)

## [0.10.0] — 2026-03-25 (Full Feature Release)

### Added
- **Query & Audit Engine**: `atlast search`, `atlast audit`, `atlast trace`, `atlast timeline` — full CLI query suite with `--json` for agent consumption
- **Per-agent Rate Limiting**: Configurable per-agent rate limits on server
- **Local Web Dashboard**: `atlast dashboard` launches problem-oriented UI at localhost:3827
  - Overview with auto-detected issues (error spikes, confidence drops, latency anomalies)
  - Activity tab with agent/error filters
  - Full-text search across 10 fields (including date, agent)
  - Evidence chain trace visualization with step-by-step input/output
  - Click any record to expand vault content
- **MCP Query Tools**: `atlast-ecp-mcp` stdio server for AI agent integration
- **Demo Data Generator**: `atlast demo --days 60` creates 2 realistic scenarios (Research Agent + Code Review Agent)
- **Vault V2 (Proxy)**: Smart deduplication — stores only new content per turn, not full conversation history. 13x storage reduction for long conversations. Government-grade audit trail with SHA-256 hash verification.
- **Dashboard Test Guide**: `docs/DASHBOARD-TEST-GUIDE.md` with 2 real scenario walkthroughs

### Fixed
- **Critical: EAS Fail-Closed** — production never generates fake UIDs on EAS failure
- **Critical: Auth Enforced** — production rejects unauthenticated batch uploads
- **Critical: Anchor Coordinator** — prevents concurrent anchor races
- Search now includes date and agent fields — clicking Detected Issue cards correctly filters
- SQLite search index rebuild (`atlast index`) handles edge cases

### Changed
- docs/api-reference.md updated: sepolia → base-mainnet (reflects actual production)
- Python SDK version: 0.9.0 → 0.10.0
- TypeScript SDK version: 0.2.2 → 0.3.0

## [0.9.0] — 2026-03-24 (Production Launch — All Rounds Complete)

### Added
- **P1 Cloud Backup**: BIP39 12-word mnemonic recovery, AES-256-GCM encrypted vault backup, `atlast recover` CLI, auto-detect iCloud/Dropbox
- **P4 Base Mainnet**: EAS deployment LIVE on Base (chain_id 8453), first mainnet attestation
- **P7 Dashboard v0.1**: Static dashboard deployed to GitHub Pages
- **P8 Onboarding flow**: Interactive onboarding page
- **P9 Docs site**: VitePress 22-page documentation at docs.weba0.com
- **P6 Web verify page**: Zero-dependency SPA for batch/attestation verification
- **ST3 Stability test**: 24h long-running stability test script
- **Cross-SDK interop**: 14/14 tests (Python↔TS hash+merkle identical)
- Server `GET /v1/agents/{did}/records` endpoint for record sync
- GitHub Pages CI deployment for docs + dashboard + onboarding + verify
- Custom domain docs.weba0.com with base path routing
- Production stress tests ST1-ST4 all passing
- Content Vault + Proof Package + `atlast inspect/proof` CLI commands

### Fixed
- `batch_ts` Integer→BigInteger (Unix ms exceeds int32)
- `DateTime→TIMESTAMP(timezone=True)` for asyncpg tz-aware compat
- mypy langchain.py callback signatures updated for latest langchain-core
- Server tests importable from repo root (conftest.py sys.path fix)
- verify.weba0.com consolidated into docs.weba0.com/verify/

### Changed
- EAS chain switched from Sepolia to Base Mainnet
- SDK retry with exponential backoff (3 attempts)
- API Key management + direct batch upload on ECP Server

## [0.8.1] — 2026-03-23 (Phase 7 — Deep Audit + Quality)

### Fixed
- **CRITICAL**: Chain hash computation missing 5 optional fields (cost_usd, parent_agent, session_id, delegation_id, delegation_depth) — records with these fields would fail verification
- **CRITICAL**: Cross-SDK hash inconsistency — TS SDK `delete sig` vs Python `sig=""`, shallow vs deep key sorting
- LiteLLM streaming path missing `session_id` in `_RecordedStream` call
- mypy type errors in `autogen.py` (dict inference) and `wrap.py` (Optional[str])

### Added
- Multi-agent delegation fields: `session_id`, `delegation_id`, `delegation_depth` across entire stack
- `chain_integrity` real-time signal in batch upload (no longer hardcoded 1.0)
- `speed_anomaly` as 8th behavioral flag in ECP-SPEC §3
- Server stats persistence via PostgreSQL (survives restarts)
- EAS attestation UID precise extraction from Attested event logs
- Super-batch aggregation design doc
- 15 delegation-specific tests (Python 11 + TS 4)
- `create_minimal_record()` explicit delegation parameters
- `stableStringify()` in TS SDK for cross-SDK hash consistency

### Changed
- TS SDK field names aligned with ECP-SPEC: `agent_id`→`agent`, `step_type`→`action`, `input_hash`→`in_hash`, `output_hash`→`out_hash`
- Test count: 750 → **765** (Python 680 + Server 42 + TS 43)

## [0.8.0] — 2026-03-21 (Phase 5)

### Added
- Framework adapter examples (`examples/langchain_demo.py`, `crewai_demo.py`, `autogen_demo.py`)
- Adapter integration README (`sdk/python/atlast_ecp/adapters/README.md`)
- 21 edge-case adapter tests (total: 50 adapter tests)
- 34 proxy unit tests (`tests/test_proxy.py`)
- Streaming response recording (`_RecordedStream` in `wrap.py`) — zero latency impact
- PostgreSQL integration (SQLAlchemy async, `attestations` + `anchor_logs` tables)
- Redis connection support
- Sentry error monitoring (3+ consecutive cron failures auto-reported)
- Prometheus metrics (`/metrics` endpoint: anchor/webhook/merkle/cron counters)
- Rate limiting (60/min via SlowAPI)
- Webhook retry with exponential backoff (3 attempts)
- E2E full chain verification (7/7 endpoints tested)
- TS SDK v0.2.0 published to npm as `@atlast/sdk`
- PyPI v0.8.0 published via GitHub Actions trusted publishing
- Whitepaper v2.2 (EN 102KB + ZH 66KB, 14 chapters, 9 Mermaid diagrams)
- Litepaper v1.0 (EN + ZH)
- INTERFACE-CONTRACT.md — canonical API reference
- ARCHITECTURE.md — system architecture documentation

### Changed
- Monorepo restructure: `atlast-ecp-server` merged into `server/`, SDKs reorganized to `sdk/{python,typescript,go}/`
- Server version bumped to 1.0.0
- Custom domain `api.weba0.com` with TLS 1.3

### Fixed
- TS SDK empty Merkle tree hash consistency (now matches Python SDK + Server)
- TS SDK `ecp_version` aligned to `"0.1"` (was `"0.5"`)
- INTERFACE-CONTRACT.md batch payload documentation accuracy
- Deep audit: 13 issues found and fixed across SDK/Server

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
