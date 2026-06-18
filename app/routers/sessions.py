"""
Sessions router — questionnaire session lifecycle.

Endpoints:
  POST  /v1/tax/sessions                       start a new session
  GET   /v1/tax/sessions/{id}                  get session state
  PATCH /v1/tax/sessions/{id}/answers          save answers progressively
  POST  /v1/tax/sessions/{id}/complete         compute required forms, mark complete
  GET   /v1/tax/sessions/{id}/required-forms   fetch required forms for a completed session
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import get_db
from app.engine import get_rule_engine
from app.models import (
    QuestionnaireSessionModel,
    SessionOut,
    TaxQuestionModel,
    TaxPeriodModel,
)

router = APIRouter(prefix="/v1/tax/sessions", tags=["sessions"])


# ── Request schemas ───────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    tax_year: int | None = None
    entity_type: str = "individual"


class UpdateAnswersRequest(BaseModel):
    answers: dict[str, Any]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(session_id: str) -> QuestionnaireSessionModel:
    async with get_db() as db:
        result = await db.execute(
            select(QuestionnaireSessionModel).where(
                QuestionnaireSessionModel.id == session_id
            )
        )
        session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "Session not found", "code": "SESSION_NOT_FOUND", "details": {}, "request_id": ""},
        )
    return session


async def _fetch_period(tax_year: int) -> TaxPeriodModel | None:
    """Fetch the tax period for a given year (used in concurrent startup fetch)."""
    async with get_db() as db:
        result = await db.execute(
            select(TaxPeriodModel).where(TaxPeriodModel.tax_year == tax_year)
        )
        return result.scalar_one_or_none()


async def _fetch_questions() -> list[TaxQuestionModel]:
    """Fetch all questionnaire questions (used in concurrent startup fetch)."""
    async with get_db() as db:
        result = await db.execute(
            select(TaxQuestionModel).order_by(TaxQuestionModel.sort_order)
        )
        return result.scalars().all()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=SessionOut, status_code=201)
async def create_session(req: CreateSessionRequest):
    """
    Start a new questionnaire session.

    Defaults: tax_year = current year − 1, entity_type = "individual".
    Concurrently fetches the tax period metadata and the question catalogue
    to hydrate the session response efficiently (asyncio.gather).
    """
    from datetime import date as _date

    tax_year = req.tax_year or (_date.today().year - 1)

    # Concurrent fetch: tax period + questions (no dependency between them)
    period, questions = await asyncio.gather(
        _fetch_period(tax_year),
        _fetch_questions(),
    )

    session = QuestionnaireSessionModel(
        id=str(uuid.uuid4()),
        tax_year=tax_year,
        entity_type=req.entity_type,
        answers={},
        required_forms=None,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )

    async with get_db() as db:
        db.add(session)
        await db.flush()
        await db.refresh(session)

    return session


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str):
    """Return current state of a questionnaire session."""
    return await _get_or_404(session_id)


@router.get("/{session_id}/required-forms")
async def get_required_forms(session_id: str):
    """
    Return the required forms for a completed session.

    Returns 404 if session not found, 409 if session is not yet completed.
    """
    session = await _get_or_404(session_id)
    if session.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Session not yet completed — call POST /complete first",
                "code": "SESSION_NOT_COMPLETED",
                "details": {"status": session.status},
                "request_id": "",
            },
        )
    return {
        "session_id": session.id,
        "tax_year": session.tax_year,
        "status": session.status,
        "required_forms": session.required_forms or [],
    }


@router.patch("/{session_id}/answers", response_model=SessionOut)
async def update_answers(session_id: str, req: UpdateAnswersRequest):
    """
    Progressively save answers to a session.

    New answers are merged (shallow) into existing answers — partial updates
    are supported, no need to re-send all answers each call.
    """
    session = await _get_or_404(session_id)
    if session.status == "completed":
        raise HTTPException(
            status_code=409,
            detail={"error": "Session already completed", "code": "SESSION_COMPLETED", "details": {}, "request_id": ""},
        )

    merged = {**(session.answers or {}), **req.answers}

    async with get_db() as db:
        result = await db.execute(
            select(QuestionnaireSessionModel).where(
                QuestionnaireSessionModel.id == session_id
            )
        )
        s = result.scalar_one()
        s.answers = merged
        await db.flush()
        await db.refresh(s)

    return s


@router.post("/{session_id}/complete", response_model=SessionOut)
async def complete_session(session_id: str):
    """
    Complete a session by evaluating form-requirement rules against saved answers.

    - Runs the rule engine via anyio.to_thread.run_sync() to avoid blocking
      the event loop for large rule sets
    - Attaches form details for each matched form
    - Marks session as completed with timestamp
    - Returns updated session with required_forms populated
    """
    session = await _get_or_404(session_id)
    if session.status == "completed":
        return session

    engine = get_rule_engine()

    # Build the index if needed, then evaluate synchronously offloaded to thread
    if not engine._built:
        await engine.build()

    answers_snapshot = dict(session.answers or {})
    tax_year = session.tax_year

    # Offload potentially-CPU-heavy rule evaluation off the async event loop
    matched = await engine.evaluate(
        answers=answers_snapshot,
        tax_year=tax_year,
    )

    now = datetime.now(timezone.utc)
    async with get_db() as db:
        result = await db.execute(
            select(QuestionnaireSessionModel).where(
                QuestionnaireSessionModel.id == session_id
            )
        )
        s = result.scalar_one()
        s.required_forms = matched
        s.status = "completed"
        s.completed_at = now
        await db.flush()
        await db.refresh(s)

    return s
