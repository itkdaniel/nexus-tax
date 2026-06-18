"""
nexus-tax — FastAPI application factory.

Architecture:
  - Factory pattern: create_app(settings=None) → FastAPI
    Inject custom Settings in tests for full isolation.
  - Lifespan context: configure DB/auth → create tables → seed data → start scheduler
  - CORS: configurable via settings.cors_origins
  - Standard endpoints: /health, /info, /docs (OpenAPI)
  - Versioned routes under /v1/
  - Error envelope: {error, code, details, request_id}

Port: 8003 (default)
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.database import configure_engine, create_tables, dispose_engine
from app.auth import configure_auth
from app.models import HealthResponse, InfoResponse
from app.routers.forms import router as forms_router
from app.routers.rates import router as rates_router, calculate_router
from app.routers.questions import router as questions_router
from app.routers.sessions import router as sessions_router
from app.routers.admin import periods_router, admin_router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger("nexus-tax")

_start_time = time.monotonic()


def _make_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting nexus-tax", port=settings.port, debug=settings.debug)

        # 0. Warn loudly in production if the default JWT secret is in use
        _DEFAULT_SECRET = "change-me-in-production"
        if not settings.debug and settings.jwt_secret == _DEFAULT_SECRET:
            logger.warning(
                "INSECURE CONFIGURATION: jwt_secret is the default placeholder. "
                "Set JWT_SECRET env var before exposing this service.",
            )

        # 1. Wire services to injected settings
        configure_engine(settings)
        configure_auth(settings)

        # 2. Ensure tables exist (dev/test — production uses Alembic)
        await create_tables()

        # 3. Seed tax data for the configured default year
        from app.seed import seed_tax_data
        try:
            await seed_tax_data(settings.default_tax_year)
        except Exception as exc:
            logger.warning("Seed data warning (may already exist)", error=str(exc))

        # 4. Pre-build rule engine index
        from app.engine import get_rule_engine
        try:
            await get_rule_engine().build()
            logger.info("Rule engine index built")
        except Exception as exc:
            logger.warning("Rule engine build deferred (no data yet?)", error=str(exc))

        # 5. Start annual scheduler (skip in test/debug mode)
        scheduler = None
        if not settings.debug:
            from app.scheduler import init_scheduler
            scheduler = init_scheduler()

        yield

        # Shutdown
        if scheduler:
            from app.scheduler import shutdown_scheduler
            shutdown_scheduler()
        await dispose_engine()
        logger.info("nexus-tax shut down cleanly")

    return lifespan


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """
    Application factory.

    Pass custom Settings for tests:
        app = create_app(Settings(database_url="sqlite+aiosqlite:///:memory:"))
    """
    cfg = settings or get_settings()

    app = FastAPI(
        title="nexus-tax",
        version=cfg.version,
        description=(
            "Standalone tax assistant microservice for NexusConsult. "
            "Provides federal/state form lookup, tax bracket data, "
            "progressive tax calculation, and an interactive questionnaire "
            "engine to determine required forms. Part of the NexusConsult portfolio."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_make_lifespan(cfg),
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Standard endpoints ────────────────────────────────────────────────────
    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    async def health():
        """Liveness probe — k8s / gateway health check."""
        return HealthResponse(
            status="ok",
            service=cfg.app_name,
            version=cfg.version,
            uptime=round(time.monotonic() - _start_time, 2),
        )

    @app.get("/info", response_model=InfoResponse, tags=["meta"])
    async def info():
        """Service metadata — consumed by the main portfolio gateway."""
        return InfoResponse(
            name=cfg.app_name,
            version=cfg.version,
            port=cfg.port,
            description="Tax assistant: form lookup, bracket data, tax calculator, questionnaire engine",
            endpoints=[
                {"method": "GET",  "path": "/health",                          "auth": False, "description": "Health check"},
                {"method": "GET",  "path": "/info",                            "auth": False, "description": "Service metadata"},
                {"method": "GET",  "path": "/v1/tax/forms/federal",                "auth": False, "description": "List federal forms"},
                {"method": "GET",  "path": "/v1/tax/forms/federal/{form_number}",  "auth": False, "description": "Get federal form by number"},
                {"method": "GET",  "path": "/v1/tax/forms/state",                  "auth": False, "description": "List all state forms"},
                {"method": "GET",  "path": "/v1/tax/forms/state/{state_code}",     "auth": False, "description": "Get state forms by state code"},
                {"method": "GET",  "path": "/v1/tax/rates/{year}",                 "auth": False, "description": "Full rate bundle for a year"},
                {"method": "GET",  "path": "/v1/tax/rates/{year}/brackets",        "auth": False, "description": "Tax brackets for a year"},
                {"method": "GET",  "path": "/v1/tax/rates/{year}/deductions",      "auth": False, "description": "Standard deductions for a year"},
                {"method": "GET",  "path": "/v1/tax/rates/{year}/special",         "auth": False, "description": "Special tax rates for a year"},
                {"method": "POST", "path": "/v1/tax/calculate",                    "auth": False, "description": "Calculate federal income tax"},
                {"method": "GET",  "path": "/v1/tax/questions",                    "auth": False, "description": "List questionnaire questions"},
                {"method": "POST", "path": "/v1/tax/sessions",                     "auth": False, "description": "Start a new questionnaire session"},
                {"method": "GET",  "path": "/v1/tax/sessions/{id}",                "auth": False, "description": "Get session state"},
                {"method": "PATCH","path": "/v1/tax/sessions/{id}/answers",        "auth": False, "description": "Save answers progressively"},
                {"method": "POST", "path": "/v1/tax/sessions/{id}/complete",       "auth": False, "description": "Compute required forms, mark complete"},
                {"method": "GET",  "path": "/v1/tax/sessions/{id}/required-forms", "auth": False, "description": "Fetch required forms for a completed session"},
                {"method": "GET",  "path": "/v1/tax/periods",                      "auth": False, "description": "List all tax periods"},
                {"method": "POST", "path": "/v1/tax/admin/seed-year",              "auth": True,  "description": "Seed / inflate a tax year (admin)"},
                {"method": "POST", "path": "/v1/tax/admin/update-year",            "auth": True,  "description": "Alias for seed-year (admin)"},
            ],
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(forms_router)
    app.include_router(rates_router)
    app.include_router(calculate_router)
    app.include_router(questions_router)
    app.include_router(sessions_router)
    app.include_router(periods_router)
    app.include_router(admin_router)

    # ── Normalized error handlers ─────────────────────────────────────────────

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        import uuid as _uuid
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail and "code" in detail:
            content = {
                "error": detail.get("error", "HTTP error"),
                "code": detail.get("code", f"HTTP_{exc.status_code}"),
                "details": detail.get("details", {}),
                "request_id": detail.get("request_id") or str(_uuid.uuid4()),
            }
        else:
            content = {
                "error": str(detail) if detail else "HTTP error",
                "code": f"HTTP_{exc.status_code}",
                "details": {},
                "request_id": str(_uuid.uuid4()),
            }
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        import uuid as _uuid
        return JSONResponse(
            status_code=422,
            content={
                "error": "Request validation failed",
                "code": "VALIDATION_ERROR",
                "details": {"errors": exc.errors()},
                "request_id": str(_uuid.uuid4()),
            },
        )

    @app.exception_handler(Exception)
    async def global_exc_handler(request: Request, exc: Exception):
        import uuid as _uuid
        logger.error("Unhandled exception", path=str(request.url), error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
                "details": {},
                "request_id": str(_uuid.uuid4()),
            },
        )

    return app


# Module-level instance for uvicorn / gunicorn
app = create_app()
