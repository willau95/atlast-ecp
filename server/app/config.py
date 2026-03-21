"""ECP Server Configuration"""
import os


class Settings:
    # EAS
    EAS_PRIVATE_KEY: str = os.getenv("EAS_PRIVATE_KEY", "")
    EAS_SCHEMA_UID: str = os.getenv("EAS_SCHEMA_UID", "0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e")
    EAS_CHAIN: str = os.getenv("EAS_CHAIN", "sepolia")
    EAS_STUB_MODE: str = os.getenv("EAS_STUB_MODE", "true")

    # Webhook (Atlas → LLaChat)
    ECP_WEBHOOK_URL: str = os.getenv("ECP_WEBHOOK_URL", "https://api.llachat.com/v1/internal/ecp-webhook")
    ECP_WEBHOOK_TOKEN: str = os.getenv("ECP_WEBHOOK_TOKEN", "")

    # LLaChat Internal API (for pulling pending batches)
    LLACHAT_API_URL: str = os.getenv("LLACHAT_API_URL", "https://api.llachat.com")
    LLACHAT_INTERNAL_TOKEN: str = os.getenv("LLACHAT_INTERNAL_TOKEN", "")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Server
    PORT: int = int(os.getenv("PORT", "8080"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")

    # Cron
    ANCHOR_INTERVAL_MINUTES: int = int(os.getenv("ANCHOR_INTERVAL_MINUTES", "60"))

    # Monitoring
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

    # CORS
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "https://llachat.com,https://www.llachat.com,https://weba0.com,https://www.weba0.com"
    ).split(",")


settings = Settings()
