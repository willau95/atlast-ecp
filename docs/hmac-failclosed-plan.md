# HMAC Fail-Closed Switch Plan

**Date:** 2026-03-23  
**Status:** Planned for post-Phase 6  
**Parties:** Atlas (ECP Server), Alex (LLaChat)

## Current State

- Webhook HMAC: **fail-open** (missing signature = log warning, still process)
- Header: `X-ECP-Signature: sha256={hmac_hex}`
- HMAC key: `X-ECP-Webhook-Token` (64-char hex, stored as Railway env var)
- HMAC input: raw HTTP body bytes (not re-serialized)

## Switch Plan

### Prerequisites (Atlas)
1. ✅ All webhook calls include `X-ECP-Signature` header
2. ✅ HMAC computed with `hmac.new(key, body, hashlib.sha256).hexdigest()`
3. ✅ Verify test: send webhook with correct signature → Alex accepts
4. ⏳ Verify test: send webhook with wrong signature → Alex rejects (after switch)

### Switch Steps (Alex)
1. Alex changes ONE line: `if not signature: log_warning(...)` → `if not signature: raise 401`
2. Alex deploys to staging, Atlas sends test webhooks
3. Verify: correct sig → 200, wrong sig → 401, missing sig → 401
4. Alex deploys to production
5. Monitor for 24h — if any legitimate webhooks fail, revert to fail-open

### Rollback
- Alex reverts the one-line change (fail-closed → fail-open)
- No data loss — failed webhooks are retried by Atlas (3× exponential backoff)

### Timeline
- **Phase 6 complete**: Atlas confirms all webhook calls signed ✅
- **Phase 7 Week 1**: Alex switches to fail-closed on staging
- **Phase 7 Week 1**: E2E test with Atlas
- **Phase 7 Week 2**: Production switch

## Verification Script

```bash
# Atlas sends test webhook
curl -X POST https://api.llachat.com/v1/internal/ecp-webhook \
  -H "Content-Type: application/json" \
  -H "X-ECP-Webhook-Token: $TOKEN" \
  -H "X-ECP-Signature: sha256=$(echo -n '$BODY' | openssl dgst -sha256 -hmac $TOKEN | cut -d' ' -f2)" \
  -d '$BODY'

# Expected: 200 OK
# Without signature header: should get 401 after switch
```
