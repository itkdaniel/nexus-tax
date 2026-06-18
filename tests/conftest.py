"""
Shared test fixtures for nexus-tax.

All tests use an in-memory SQLite database (via aiosqlite) — no external
services required. The database is created fresh for each test function
via the `app` and `client` fixtures.

Fixtures:
  settings   — overridden Settings with SQLite URL
  app        — fully created FastAPI app (lifespan runs: tables + seed)
  client     — httpx.AsyncClient bound to the app
  seeded_app — alias for `app` (backwards compat)
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from httpx import AsyncClient, ASGITransport

from app.config import Settings
from app.main import create_app
from app.engine import reset_rule_engine


@pytest.fixture(scope="function")
def settings() -> Settings:
    """Fresh in-memory SQLite settings for each test."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="test-secret-nexus-tax",
        debug=True,
        default_tax_year=2024,
        port=8003,
    )


@pytest_asyncio.fixture(scope="function")
async def app(settings):
    """
    Create a fresh app instance with lifespan (tables created + 2024 data seeded).
    Also resets the rule engine singleton so each test starts clean.
    """
    reset_rule_engine()
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application
    reset_rule_engine()


@pytest_asyncio.fixture(scope="function")
async def client(app):
    """httpx.AsyncClient bound to the test app — no real HTTP server needed."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def admin_client(app, settings):
    """
    AsyncClient that automatically injects a valid admin JWT header.
    Uses the same HMAC-SHA256 scheme as the main portfolio.
    """
    import base64
    import hashlib
    import hmac
    import json
    import time

    payload = {"sub": "1", "role": "admin", "exp": int(time.time()) + 86400}
    header = {"alg": "HS256", "typ": "JWT"}

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).rstrip(b"=").decode()

    h64, p64 = b64(header), b64(payload)
    sig = hmac.new(settings.jwt_secret.encode(), f"{h64}.{p64}".encode(), hashlib.sha256).digest()
    s64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    token = f"{h64}.{p64}.{s64}"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac
