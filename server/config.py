"""
ECP Reference Server — Configuration

All settings via environment variables with sensible defaults.
"""

import os


class Settings:
    DB_PATH: str = os.getenv("ECP_DB_PATH", "ecp_server.db")
    HOST: str = os.getenv("ECP_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("ECP_PORT", "8900"))
    LOG_LEVEL: str = os.getenv("ECP_LOG_LEVEL", "info")
    CORS_ORIGINS: str = os.getenv("ECP_CORS_ORIGINS", "*")
    # Trust score weights (must sum to 1.0)
    WEIGHT_RELIABILITY: float = float(os.getenv("ECP_WEIGHT_RELIABILITY", "0.4"))
    WEIGHT_TRANSPARENCY: float = float(os.getenv("ECP_WEIGHT_TRANSPARENCY", "0.3"))
    WEIGHT_EFFICIENCY: float = float(os.getenv("ECP_WEIGHT_EFFICIENCY", "0.2"))
    WEIGHT_AUTHORITY: float = float(os.getenv("ECP_WEIGHT_AUTHORITY", "0.1"))


settings = Settings()
