"""
Rates router — tax brackets, standard deductions, special rates, calculator.

Endpoints:
  GET  /v1/rates/{year}                 full rate bundle (brackets + deductions + special)
  GET  /v1/rates/{year}/brackets        brackets for year (optional ?filing_status=single)
  GET  /v1/rates/{year}/deductions      standard deductions for year
  GET  /v1/rates/{year}/special         special tax rates for year
  POST /v1/calculate                    compute federal tax for income + status + year
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database import get_db
from app.models import (
    TaxBracketModel,
    TaxBracketOut,
    StandardDeductionModel,
    StandardDeductionOut,
    SpecialTaxRateModel,
    SpecialTaxRateOut,
    CalculateResponse,
)
from app.engine import calculate_tax

router = APIRouter(prefix="/v1/tax/rates", tags=["rates"])

VALID_STATUSES = {"single", "mfj", "mfs", "hoh", "qw"}


@router.get("/{year}", tags=["rates"])
async def get_rate_bundle(
    year: int,
    filing_status: Optional[str] = Query(None),
):
    """Full rate bundle for a given year: brackets + standard deductions + special rates."""
    async with get_db() as db:
        # Brackets
        b_stmt = select(TaxBracketModel).where(TaxBracketModel.tax_year == year).order_by(
            TaxBracketModel.filing_status, TaxBracketModel.income_from
        )
        if filing_status:
            b_stmt = b_stmt.where(TaxBracketModel.filing_status == filing_status)
        brackets = (await db.execute(b_stmt)).scalars().all()

        # Standard deductions
        d_stmt = select(StandardDeductionModel).where(StandardDeductionModel.tax_year == year)
        deductions = (await db.execute(d_stmt)).scalars().all()

        # Special rates
        s_stmt = select(SpecialTaxRateModel).where(SpecialTaxRateModel.tax_year == year)
        special = (await db.execute(s_stmt)).scalars().all()

    if not brackets and not deductions:
        raise HTTPException(
            status_code=404,
            detail={"error": f"No rate data for year {year}", "code": "YEAR_NOT_FOUND", "details": {}, "request_id": ""},
        )

    return {
        "tax_year": year,
        "brackets": [TaxBracketOut.model_validate(b) for b in brackets],
        "standard_deductions": [StandardDeductionOut.model_validate(d) for d in deductions],
        "special_rates": [SpecialTaxRateOut.model_validate(s) for s in special],
    }


@router.get("/{year}/brackets", response_model=list[TaxBracketOut])
async def get_brackets(
    year: int,
    filing_status: Optional[str] = Query(None),
):
    """Tax brackets for a given year, optionally filtered by filing status."""
    async with get_db() as db:
        stmt = (
            select(TaxBracketModel)
            .where(TaxBracketModel.tax_year == year)
            .order_by(TaxBracketModel.filing_status, TaxBracketModel.income_from)
        )
        if filing_status:
            stmt = stmt.where(TaxBracketModel.filing_status == filing_status)
        result = await db.execute(stmt)
        brackets = result.scalars().all()
    return brackets


@router.get("/{year}/deductions", response_model=list[StandardDeductionOut])
async def get_deductions(year: int):
    """Standard deductions for all filing statuses for a given year."""
    async with get_db() as db:
        result = await db.execute(
            select(StandardDeductionModel).where(StandardDeductionModel.tax_year == year)
        )
        deductions = result.scalars().all()
    return deductions


@router.get("/{year}/special", response_model=list[SpecialTaxRateOut])
async def get_special_rates(year: int):
    """Special tax rates (FICA, SE, NIIT, AMT, cap-gains) for a given year."""
    async with get_db() as db:
        result = await db.execute(
            select(SpecialTaxRateModel).where(SpecialTaxRateModel.tax_year == year)
        )
        rates = result.scalars().all()
    return rates


# ── Calculate endpoint (separate prefix) ─────────────────────────────────────
calculate_router = APIRouter(prefix="/v1/tax", tags=["calculate"])


class CalculateRequest(BaseModel):
    income: float = Field(..., gt=0, description="Gross income before deductions")
    filing_status: str = Field(..., description="single | mfj | mfs | hoh | qw")
    tax_year: int = Field(..., ge=1900, le=2099, description="Tax year")
    age_65: bool = Field(False, description="Taxpayer (or spouse for MFJ) is 65+")
    blind: bool = Field(False, description="Taxpayer (or spouse for MFJ) is blind")


@calculate_router.post("/calculate", response_model=CalculateResponse)
async def post_calculate(req: CalculateRequest):
    """
    Compute federal income tax using progressive brackets.

    Returns gross income, standard deduction, taxable income, federal tax,
    effective rate, marginal rate, and per-bracket breakdown.
    """
    if req.filing_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"Invalid filing_status '{req.filing_status}'",
                "code": "INVALID_FILING_STATUS",
                "details": {"valid": list(VALID_STATUSES)},
                "request_id": "",
            },
        )
    try:
        result = await calculate_tax(
            income=req.income,
            filing_status=req.filing_status,
            tax_year=req.tax_year,
            age_65=req.age_65,
            blind=req.blind,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": str(exc), "code": "RATE_DATA_NOT_FOUND", "details": {}, "request_id": ""},
        )
    return result
