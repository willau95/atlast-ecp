"""
/v1/scoring/rules — Public API for ATLAST Scoring Rules.

Returns the current scoring rules that SDKs use to classify and score records.
No authentication required (rules are public).

SDKs call this endpoint to get the latest rules, cached locally for 24h.
When we update rules here, all SDKs pick up changes within 24h — zero user action.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/scoring", tags=["scoring"])

# ─── Current Scoring Rules ────────────────────────────────────────────────────
# This is the single source of truth for scoring rules.
# Update this dict to change how ALL agents are scored globally.
# SDKs cache this for 24h, so changes propagate within a day.

SCORING_RULES = {
    "version": "1.0",
    "updated_at": "2026-04-05",

    "classification": [
        {
            "label": "heartbeat",
            "description": "System heartbeat message, not a user interaction",
            "conditions": {"any_flag": ["heartbeat"]},
        },
        {
            "label": "system_error",
            "description": "Billing, auth, or quota error from the provider",
            "conditions": {"any_flag": ["provider_error"]},
            "output_patterns": [
                "extra usage", "billing", "quota", "Third-party apps",
                "api_key", "invalid_request_error", "authentication",
                "insufficient_quota", "account", "plan limits",
            ],
        },
        {
            "label": "infra_error",
            "description": "Provider infrastructure failure",
            "conditions": {"any_flag": ["http_5xx", "infra_error"]},
            "output_patterns": [
                "rate limit", "overloaded", "capacity", "maintenance",
                "service_unavailable", "internal_server_error",
            ],
        },
        {
            "label": "tool_intermediate",
            "description": "Mid-chain API call (tool_call or tool_result continuation)",
            "conditions": {
                "any_flag": ["has_tool_calls", "tool_continuation"],
                "all_flag": [],
            },
            "require_empty_text_output": True,
        },
        {
            "label": "interaction",
            "description": "Real user-agent interaction (default)",
            "conditions": {"default": True},
        },
    ],

    "scoring": {
        "exclude_from_scoring": ["heartbeat", "system_error", "infra_error", "tool_intermediate"],
        "exclude_from_latency": ["heartbeat", "infra_error", "system_error"],
        "high_latency_threshold_ms": 10000,
        "incomplete_max_chars": 5,
    },

    "custom_rules": [],
}


@router.get("/rules")
async def get_scoring_rules():
    """
    Get current scoring rules.

    SDKs call this to stay in sync. Response is cached by SDKs for 24h.
    No authentication required — rules are public.
    """
    return SCORING_RULES
