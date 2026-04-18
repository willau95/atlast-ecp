"""ECP Server Configuration"""
import os


# Development environment whitelist. Any ENVIRONMENT value NOT in this set is
# treated as production for security decisions — fail-closed against typos
# like "prod", "PRODUCTION", staging misconfigurations, or a missing env var.
# Callers do: `settings.ENVIRONMENT.strip().lower() in _DEV_ENVIRONMENTS`.
_DEV_ENVIRONMENTS = frozenset({"development", "dev", "test", "testing", "local"})


class Settings:
    # EAS
    EAS_PRIVATE_KEY: str = os.getenv("EAS_PRIVATE_KEY", "")
    EAS_SCHEMA_UID: str = os.getenv("EAS_SCHEMA_UID", "0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e")
    EAS_CHAIN: str = os.getenv("EAS_CHAIN", "sepolia")
    # Empty default = not configured. Startup validation below forces the
    # operator to make an explicit choice in any non-dev environment, so
    # production can never silently run in stub mode (fake attestations).
    EAS_STUB_MODE: str = os.getenv("EAS_STUB_MODE", "")

    # Webhook (Atlas → LLaChat)
    ECP_WEBHOOK_URL: str = os.getenv("ECP_WEBHOOK_URL", "https://api.llachat.com/v1/internal/ecp-webhook")
    ECP_WEBHOOK_TOKEN: str = os.getenv("ECP_WEBHOOK_TOKEN", "")

    # LLaChat Internal API (for pulling pending batches)
    LLACHAT_API_URL: str = os.getenv("LLACHAT_API_URL", "https://api.llachat.com")
    LLACHAT_INTERNAL_TOKEN: str = os.getenv("LLACHAT_INTERNAL_TOKEN", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Server
    PORT: int = int(os.getenv("PORT", "8080"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")

    # Cron
    ANCHOR_INTERVAL_MINUTES: int = int(os.getenv("ANCHOR_INTERVAL_MINUTES", "60"))

    # Anchor policy (defense against gas-waste via tiny batches)
    #
    # Anchor fires only when EITHER:
    #   (a) len(pending) >= MIN_ANCHOR_BATCHES AND total_records >= MIN_ANCHOR_RECORDS
    #   (b) oldest_pending_age_hours >= MAX_ANCHOR_WAIT_HOURS (anti-starvation for legit small users)
    # Once firing, batches are merged into a single super-batch when
    # len >= SUPER_BATCH_MIN_SIZE (one on-chain tx amortized across all).
    # Previous defaults (SUPER_BATCH_MIN_SIZE=5, no records/wait gate) allowed
    # an attacker to flood 5 single-record batches to force an immediate,
    # expensive on-chain tx per 5 records.
    MIN_ANCHOR_BATCHES: int = int(os.getenv("MIN_ANCHOR_BATCHES", "10"))
    MIN_ANCHOR_RECORDS: int = int(os.getenv("MIN_ANCHOR_RECORDS", "100"))
    MAX_ANCHOR_WAIT_HOURS: int = int(os.getenv("MAX_ANCHOR_WAIT_HOURS", "168"))  # 7 days
    SUPER_BATCH_MIN_SIZE: int = int(os.getenv("SUPER_BATCH_MIN_SIZE", "10"))

    # Monitoring
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

    # CORS
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "https://llachat.com,https://www.llachat.com,https://weba0.com,https://www.weba0.com,https://docs.weba0.com,https://willau95.github.io"
    ).split(",")


settings = Settings()

# ── Startup validation (fail-closed) ─────────────────────────────────────────
# Previously this block only logged warnings — a misconfigured production
# deployment could silently run with stub attestations, telling users their
# batches were "anchored" when they weren't. We now raise at import time so
# any non-dev environment must explicitly declare its EAS mode.
import logging as _logging
_startup_logger = _logging.getLogger("atlast.startup")

_env_norm = (settings.ENVIRONMENT or "").strip().lower()
_is_dev = _env_norm in _DEV_ENVIRONMENTS
_stub_norm = (settings.EAS_STUB_MODE or "").strip().lower()

if not _is_dev:
    # Production / staging / unknown: EAS mode must be explicit.
    if _stub_norm == "":
        raise RuntimeError(
            "ATLAST server startup: EAS_STUB_MODE is not configured.\n"
            f"  ENVIRONMENT={settings.ENVIRONMENT!r} is treated as production "
            "(any value outside the dev whitelist).\n"
            "  Set one of:\n"
            "    EAS_STUB_MODE=true                              (stub: no on-chain tx)\n"
            "    EAS_STUB_MODE=false + EAS_PRIVATE_KEY=<key>     (live on-chain)\n"
            "  Refusing to start rather than silently pretending to anchor."
        )
    if _stub_norm == "false" and not settings.EAS_PRIVATE_KEY:
        raise RuntimeError(
            "ATLAST server startup: EAS_STUB_MODE=false requires EAS_PRIVATE_KEY. "
            "Set the wallet private key, or switch EAS_STUB_MODE=true to run without on-chain writes."
        )
    if not settings.DATABASE_URL:
        _startup_logger.warning(
            "DATABASE_URL not set in non-dev environment — batch storage will be unavailable"
        )
else:
    # Dev whitelist: stub is the implicit, safe default when not set.
    if _stub_norm == "":
        settings.EAS_STUB_MODE = "true"
        _startup_logger.info(
            "Dev environment: defaulting EAS_STUB_MODE=true (no on-chain writes)."
        )
