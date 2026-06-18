"""
Admin router — tax period management and manual seed trigger.

All endpoints require admin JWT (role == "admin").

Endpoints:
  GET  /v1/periods             list all tax periods
  GET  /v1/periods/{year}      get a specific tax period
  POST /v1/admin/seed-year     seed a specific tax year (manual trigger)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import require_admin
from app.database import get_db
from app.models import TaxPeriodModel, TaxPeriodOut

# Public periods endpoints (no auth — matches monolith behaviour)
periods_router = APIRouter(prefix="/v1/periods", tags=["periods"])

# Admin-only endpoints
admin_router = APIRouter(prefix="/v1/admin", tags=["admin"])


@periods_router.get("", response_model=list[TaxPeriodOut])
async def list_periods():
    """List all tax periods ordered by tax year descending."""
    async with get_db() as db:
        result = await db.execute(
            select(TaxPeriodModel).order_by(TaxPeriodModel.tax_year.desc())
        )
        periods = result.scalars().all()
    return periods


@periods_router.get("/{year}", response_model=TaxPeriodOut)
async def get_period(year: int):
    """Get a specific tax period by year."""
    async with get_db() as db:
        result = await db.execute(
            select(TaxPeriodModel).where(TaxPeriodModel.tax_year == year)
        )
        period = result.scalar_one_or_none()
    if period is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Tax period {year} not found", "code": "PERIOD_NOT_FOUND", "details": {}, "request_id": ""},
        )
    return period


class SeedYearRequest(BaseModel):
    tax_year: int


@admin_router.post("/seed-year")
async def seed_year(req: SeedYearRequest, _: dict = Depends(require_admin)):
    """
    Manually trigger seeding for a specific tax year.
    Idempotent — safe to call multiple times for the same year.
    """
    from app.seed import seed_tax_data
    from app.engine import reset_rule_engine

    try:
        await seed_tax_data(req.tax_year)
        reset_rule_engine()  # force rebuild after new data
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": str(exc), "code": "SEED_FAILED", "details": {}, "request_id": ""},
        )
    return {"message": f"Tax year {req.tax_year} seeded successfully."}
