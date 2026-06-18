"""Initial schema — all nexus-tax tables.

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tax_periods ───────────────────────────────────────────────────────────
    op.create_table(
        "tax_periods",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tax_year", sa.Integer(), nullable=False, unique=True),
        sa.Column("filing_deadline", sa.Text(), nullable=False),
        sa.Column("extension_deadline", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("seeded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── federal_forms ─────────────────────────────────────────────────────────
    op.create_table(
        "federal_forms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("form_number", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("subcategory", sa.Text(), nullable=True),
        sa.Column("who_files", sa.Text(), nullable=False),
        sa.Column("provided_by", sa.Text(), nullable=True),
        sa.Column("filing_methods", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("irs_url", sa.Text(), nullable=True),
        sa.Column("instructions_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("first_tax_year", sa.Integer(), nullable=True),
        sa.Column("last_tax_year", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )

    # ── state_forms ───────────────────────────────────────────────────────────
    op.create_table(
        "state_forms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("state_code", sa.Text(), nullable=False),
        sa.Column("state_name", sa.Text(), nullable=False),
        sa.Column("form_number", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("who_files", sa.Text(), nullable=False),
        sa.Column("provided_by", sa.Text(), nullable=True),
        sa.Column("filing_methods", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("state_web_url", sa.Text(), nullable=True),
        sa.Column("has_income_tax", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_state_forms_state_code", "state_forms", ["state_code"])

    # ── tax_brackets ──────────────────────────────────────────────────────────
    op.create_table(
        "tax_brackets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("filing_status", sa.Text(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("income_from", sa.Float(), nullable=False),
        sa.Column("income_to", sa.Float(), nullable=True),
    )
    op.create_index("ix_tax_brackets_year_status", "tax_brackets", ["tax_year", "filing_status"])

    # ── standard_deductions ───────────────────────────────────────────────────
    op.create_table(
        "standard_deductions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("filing_status", sa.Text(), nullable=False),
        sa.Column("base_amount", sa.Float(), nullable=False),
        sa.Column("age65_addition", sa.Float(), nullable=False, server_default="0"),
        sa.Column("blind_addition", sa.Float(), nullable=False, server_default="0"),
    )

    # ── special_tax_rates ─────────────────────────────────────────────────────
    op.create_table(
        "special_tax_rates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("rate_type", sa.Text(), nullable=False),
        sa.Column("filing_status", sa.Text(), nullable=True),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("wage_base", sa.Float(), nullable=True),
        sa.Column("threshold_from", sa.Float(), nullable=True),
        sa.Column("threshold_to", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
    )

    # ── tax_questions ─────────────────────────────────────────────────────────
    op.create_table(
        "tax_questions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("question_key", sa.Text(), nullable=False, unique=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("input_type", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("depends_on_key", sa.Text(), nullable=True),
        sa.Column("depends_on_val", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applies_to_individual", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("applies_to_business", sa.Boolean(), nullable=False, server_default="false"),
    )

    # ── form_requirement_rules ────────────────────────────────────────────────
    op.create_table(
        "form_requirement_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("question_key", sa.Text(), nullable=False),
        sa.Column("question_value", sa.Text(), nullable=False),
        sa.Column("form_source", sa.Text(), nullable=False),
        sa.Column("form_number", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), nullable=False, server_default="required"),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_form_rules_question_key", "form_requirement_rules", ["question_key"])

    # ── questionnaire_sessions ────────────────────────────────────────────────
    op.create_table(
        "questionnaire_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False, server_default="individual"),
        sa.Column("answers", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("required_forms", sa.JSON(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("questionnaire_sessions")
    op.drop_table("form_requirement_rules")
    op.drop_table("tax_questions")
    op.drop_table("special_tax_rates")
    op.drop_table("standard_deductions")
    op.drop_table("tax_brackets")
    op.drop_table("state_forms")
    op.drop_table("federal_forms")
    op.drop_table("tax_periods")
