"""
Forms router — federal and state tax form lookup.

Endpoints:
  GET /v1/forms/federal                  list federal forms (optional ?category=)
  GET /v1/forms/federal/{form_number}    single federal form
  GET /v1/forms/state                    list all state forms (optional ?code=CA)
  GET /v1/forms/state/{state_code}       all forms for a given state
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.database import get_db
from app.models import FederalFormModel, FederalFormOut, StateFormModel, StateFormOut

router = APIRouter(prefix="/v1/tax/forms", tags=["forms"])


@router.get("/federal", response_model=list[FederalFormOut])
async def list_federal_forms(category: Optional[str] = Query(None)):
    """List all federal tax forms, optionally filtered by category."""
    async with get_db() as db:
        stmt = select(FederalFormModel).order_by(FederalFormModel.sort_order)
        if category:
            stmt = stmt.where(FederalFormModel.category == category)
        result = await db.execute(stmt)
        forms = result.scalars().all()
    return forms


@router.get("/federal/{form_number:path}", response_model=FederalFormOut)
async def get_federal_form(form_number: str):
    """Get a single federal form by form number (URL-decoded)."""
    decoded = unquote(form_number)
    async with get_db() as db:
        result = await db.execute(
            select(FederalFormModel).where(FederalFormModel.form_number == decoded)
        )
        form = result.scalar_one_or_none()
    if form is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Form '{decoded}' not found", "code": "FORM_NOT_FOUND", "details": {}, "request_id": ""},
        )
    return form


@router.get("/state", response_model=list[StateFormOut])
async def list_state_forms(code: Optional[str] = Query(None)):
    """List all state forms, optionally filtered by state code."""
    async with get_db() as db:
        stmt = select(StateFormModel).order_by(StateFormModel.state_code)
        if code:
            stmt = stmt.where(StateFormModel.state_code == code.upper())
        result = await db.execute(stmt)
        forms = result.scalars().all()
    return forms


@router.get("/state/{state_code}", response_model=list[StateFormOut])
async def get_state_forms(state_code: str):
    """Get all forms for a given two-letter state code."""
    code = state_code.upper()
    async with get_db() as db:
        result = await db.execute(
            select(StateFormModel)
            .where(StateFormModel.state_code == code)
            .order_by(StateFormModel.id)
        )
        forms = result.scalars().all()
    if not forms:
        raise HTTPException(
            status_code=404,
            detail={"error": f"No forms found for state '{code}'", "code": "STATE_NOT_FOUND", "details": {}, "request_id": ""},
        )
    return forms
