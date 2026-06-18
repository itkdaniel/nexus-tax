"""
Application configuration — reads from environment variables.
Uses pydantic-settings for type-safe, validated config with .env support.
"""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Service identity ──────────────────────────────────────────────────────
    app_name: str = "nexus-tax"
    version: str = "1.0.0"
    port: int = 8003
    debug: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://nexus:nexuspassword@localhost:5432/nexustax"

    # ── Auth (HMAC JWT forwarded from main portfolio) ─────────────────────────
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"

    # ── Tax data ──────────────────────────────────────────────────────────────
    # The most-recent completed tax year (auto-seed target at startup)
    default_tax_year: int = 2024

    # ── Portfolio gateway ─────────────────────────────────────────────────────
    portfolio_url: str = "http://localhost:5000"

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["*"]

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton — created once, shared across all requests."""
    return Settings()
