"""
Sessions router — questionnaire session lifecycle.

Endpoints:
  POST  /v1/sessions               start a new session
  GET   /v1/sessions/{id}          get session state
  PATCH /v1/sessions/{id}/answers  save answers progressively
  POST  /v1/sessions/{id}/complete compute required forms, mark complete
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import get_db
from app.engine import get_rule_engine
from app.models import QuestionnaireSessionModel, SessionOut

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=SessionOut, status_code=201)
async def create_session(req: CreateSessionRequest):
    """
    Start a new questionnaire session.

    Defaults: tax_year = current year − 1, entity_type = "individual".
    """
    from datetime import date as _date

    tax_year = req.tax_year or (_date.today().year - 1)

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

    - Runs the rule engine (O(q) single-pass)
    - Attaches form details for each matched form
    - Marks session as completed with timestamp
    - Returns updated session with required_forms populated
    """
    session = await _get_or_404(session_id)
    if session.status == "completed":
        return session

    engine = get_rule_engine()
    matched = await engine.evaluate(
        answers=session.answers or {},
        tax_year=session.tax_year,
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
