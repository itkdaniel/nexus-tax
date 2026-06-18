"""
SQLAlchemy ORM models and Pydantic v2 request/response schemas for nexus-tax.

All models mirror the TypeScript schema in shared/schema.ts.

Array columns (filing_methods) are stored as JSON for dialect compatibility —
PostgreSQL stores them as JSON, SQLite stores them as text (for tests).
JSONB columns (options, answers, required_forms) use JSON type the same way.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ═══════════════════════════════════════════════════════════════════════════════
# SQLAlchemy ORM Models
# ═══════════════════════════════════════════════════════════════════════════════

class TaxPeriodModel(Base):
    __tablename__ = "tax_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    filing_deadline: Mapped[str] = mapped_column(Text, nullable=False)
    extension_deadline: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seeded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FederalFormModel(Base):
    __tablename__ = "federal_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    form_number: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    who_files: Mapped[str] = mapped_column(Text, nullable=False)
    provided_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filing_methods: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    irs_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instructions_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_tax_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_tax_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class StateFormModel(Base):
    __tablename__ = "state_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    state_name: Mapped[str] = mapped_column(Text, nullable=False)
    form_number: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    who_files: Mapped[str] = mapped_column(Text, nullable=False)
    provided_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filing_methods: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    state_web_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_income_tax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TaxBracketModel(Base):
    __tablename__ = "tax_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    filing_status: Mapped[str] = mapped_column(Text, nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    income_from: Mapped[float] = mapped_column(Float, nullable=False)
    income_to: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class StandardDeductionModel(Base):
    __tablename__ = "standard_deductions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    filing_status: Mapped[str] = mapped_column(Text, nullable=False)
    base_amount: Mapped[float] = mapped_column(Float, nullable=False)
    age65_addition: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    blind_addition: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class SpecialTaxRateModel(Base):
    __tablename__ = "special_tax_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_type: Mapped[str] = mapped_column(Text, nullable=False)
    filing_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    wage_base: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_from: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_to: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class TaxQuestionModel(Base):
    __tablename__ = "tax_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    help_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_type: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    depends_on_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    depends_on_val: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applies_to_individual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    applies_to_business: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FormRequirementRuleModel(Base):
    __tablename__ = "form_requirement_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_key: Mapped[str] = mapped_column(Text, nullable=False)
    question_value: Mapped[str] = mapped_column(Text, nullable=False)
    form_source: Mapped[str] = mapped_column(Text, nullable=False)
    form_number: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False, default="required")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class QuestionnaireSessionModel(Base):
    __tablename__ = "questionnaire_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False, default="individual")
    answers: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    required_forms: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="in_progress")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Response Schemas
# ═══════════════════════════════════════════════════════════════════════════════

class TaxPeriodOut(BaseModel):
    id: int
    tax_year: int
    filing_deadline: str
    extension_deadline: str
    status: str
    notes: Optional[str]
    seeded_at: datetime

    model_config = {"from_attributes": True}


class FederalFormOut(BaseModel):
    id: int
    form_number: str
    title: str
    description: str
    category: str
    subcategory: Optional[str]
    who_files: str
    provided_by: Optional[str]
    filing_methods: list[str]
    irs_url: Optional[str]
    instructions_url: Optional[str]
    is_active: bool
    first_tax_year: Optional[int]
    last_tax_year: Optional[int]
    sort_order: int

    model_config = {"from_attributes": True}


class StateFormOut(BaseModel):
    id: int
    state_code: str
    state_name: str
    form_number: str
    title: str
    description: str
    category: str
    who_files: str
    provided_by: Optional[str]
    filing_methods: list[str]
    state_web_url: Optional[str]
    has_income_tax: bool
    is_active: bool

    model_config = {"from_attributes": True}


class TaxBracketOut(BaseModel):
    id: int
    tax_year: int
    filing_status: str
    rate: float
    income_from: float
    income_to: Optional[float]

    model_config = {"from_attributes": True}


class StandardDeductionOut(BaseModel):
    id: int
    tax_year: int
    filing_status: str
    base_amount: float
    age65_addition: float
    blind_addition: float

    model_config = {"from_attributes": True}


class SpecialTaxRateOut(BaseModel):
    id: int
    tax_year: int
    rate_type: str
    filing_status: Optional[str]
    rate: float
    wage_base: Optional[float]
    threshold_from: Optional[float]
    threshold_to: Optional[float]
    description: str

    model_config = {"from_attributes": True}


class TaxQuestionOut(BaseModel):
    id: int
    question_key: str
    category: str
    question_text: str
    help_text: Optional[str]
    input_type: str
    options: Optional[Any]
    is_required: bool
    depends_on_key: Optional[str]
    depends_on_val: Optional[str]
    sort_order: int
    applies_to_individual: bool
    applies_to_business: bool

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    id: str
    tax_year: int
    entity_type: str
    answers: dict[str, Any]
    required_forms: Optional[Any]
    status: str
    started_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class BracketDetail(BaseModel):
    rate: float
    income_from: float
    income_to: Optional[float]
    income_in_bracket: float
    tax_on_bracket: float


class CalculateResponse(BaseModel):
    tax_year: int
    filing_status: str
    gross_income: float
    standard_deduction: float
    taxable_income: float
    federal_tax: float
    effective_rate: float
    marginal_rate: float
    brackets_detail: list[BracketDetail]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    uptime: float


class InfoResponse(BaseModel):
    name: str
    version: str
    port: int
    description: str
    endpoints: list[dict]
