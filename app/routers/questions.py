"""
Questions router — questionnaire question catalogue.

Endpoints:
  GET /v1/questions          list all questionnaire questions
  GET /v1/questions/{key}    single question by question_key
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.database import get_db
from app.models import TaxQuestionModel, TaxQuestionOut

router = APIRouter(prefix="/v1/questions", tags=["questions"])


@router.get("", response_model=list[TaxQuestionOut])
async def list_questions():
    """
    Return all questionnaire questions ordered by sort_order.

    Questions include dependency metadata (depends_on_key / depends_on_val)
    to allow the client to build a conditional question flow.
    """
    async with get_db() as db:
        result = await db.execute(
            select(TaxQuestionModel).order_by(TaxQuestionModel.sort_order)
        )
        questions = result.scalars().all()
    return questions


@router.get("/{question_key}", response_model=TaxQuestionOut)
async def get_question(question_key: str):
    """Get a single question by its key."""
    async with get_db() as db:
        result = await db.execute(
            select(TaxQuestionModel).where(TaxQuestionModel.question_key == question_key)
        )
        q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Question '{question_key}' not found", "code": "QUESTION_NOT_FOUND", "details": {}, "request_id": ""},
        )
    return q
