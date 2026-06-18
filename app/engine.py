"""
Tax calculation engine for nexus-tax.

Two core algorithms:

1. BracketCalculator — O(b) progressive federal tax calculation.
   Given gross income, filing status, and year:
   - Fetches brackets + standard deduction from DB
   - Applies standard deduction to get taxable income
   - Walks brackets in ascending order, accumulating tax per band
   - Returns CalculateResponse with full detail

2. RuleEngine — O(q) questionnaire form-matching.
   At startup, builds lookup: {question_key: {question_value: [rules]}}
   For any set of answers, evaluates all triggers in a single pass.
   - Wildcard value "*" matches any non-empty answer
   - Results deduplicated by (form_source, form_number)
   - Sorted: required → likely → maybe
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select

from app.database import get_db
from app.models import (
    FederalFormModel,
    FormRequirementRuleModel,
    StandardDeductionModel,
    StateFormModel,
    TaxBracketModel,
    CalculateResponse,
    BracketDetail,
)


# ── Bracket Calculator ────────────────────────────────────────────────────────

async def calculate_tax(
    income: float,
    filing_status: str,
    tax_year: int,
    age_65: bool = False,
    blind: bool = False,
) -> CalculateResponse:
    """
    Compute federal income tax via progressive brackets.

    Args:
        income:       Gross income (before deduction)
        filing_status: one of single|mfj|mfs|hoh|qw
        tax_year:     Tax year (must exist in DB)
        age_65:       True if taxpayer (or spouse for MFJ) is 65+
        blind:        True if taxpayer (or spouse for MFJ) is blind

    Raises:
        ValueError: if filing_status not found or no brackets for year
    """
    async with get_db() as db:
        # Fetch standard deduction for this status + year
        deduction_row = (await db.execute(
            select(StandardDeductionModel).where(
                StandardDeductionModel.tax_year == tax_year,
                StandardDeductionModel.filing_status == filing_status,
            )
        )).scalar_one_or_none()

        if deduction_row is None:
            raise ValueError(
                f"No standard deduction found for {filing_status}/{tax_year}. "
                "Ensure the tax year is seeded."
            )

        std_deduction = deduction_row.base_amount
        # Add age-65 / blind additions (each qualifying person adds the amount)
        if age_65:
            std_deduction += deduction_row.age65_addition
        if blind:
            std_deduction += deduction_row.blind_addition

        # Fetch brackets ordered by income_from
        brackets_result = await db.execute(
            select(TaxBracketModel)
            .where(
                TaxBracketModel.tax_year == tax_year,
                TaxBracketModel.filing_status == filing_status,
            )
            .order_by(TaxBracketModel.income_from)
        )
        brackets = brackets_result.scalars().all()

    if not brackets:
        raise ValueError(
            f"No tax brackets found for {filing_status}/{tax_year}. "
            "Ensure the tax year is seeded."
        )

    taxable_income = max(0.0, income - std_deduction)

    total_tax = 0.0
    marginal_rate = 0.0
    detail: list[BracketDetail] = []

    for bracket in brackets:
        if taxable_income <= bracket.income_from:
            break
        upper = bracket.income_to if bracket.income_to is not None else float("inf")
        income_in_band = min(taxable_income, upper) - bracket.income_from
        tax_in_band = income_in_band * bracket.rate
        total_tax += tax_in_band
        marginal_rate = bracket.rate
        detail.append(BracketDetail(
            rate=bracket.rate,
            income_from=bracket.income_from,
            income_to=bracket.income_to,
            income_in_bracket=round(income_in_band, 2),
            tax_on_bracket=round(tax_in_band, 2),
        ))

    effective_rate = total_tax / income if income > 0 else 0.0

    return CalculateResponse(
        tax_year=tax_year,
        filing_status=filing_status,
        gross_income=round(income, 2),
        standard_deduction=round(std_deduction, 2),
        taxable_income=round(taxable_income, 2),
        federal_tax=round(total_tax, 2),
        effective_rate=round(effective_rate, 6),
        marginal_rate=marginal_rate,
        brackets_detail=detail,
    )


# ── Rule Engine ───────────────────────────────────────────────────────────────

class RuleEngine:
    """
    O(q) rule evaluator built from form_requirement_rules.

    Build once at startup; evaluate for each session completion.

    Lookup structure:
        {question_key: {question_value: [rule_dicts], "*": [rule_dicts]}}
    """

    def __init__(self) -> None:
        # {question_key: {question_value: [rule_rows]}}
        self._index: dict[str, dict[str, list[dict]]] = {}
        self._built = False

    async def build(self) -> None:
        """Fetch all rules from DB and build the lookup index."""
        async with get_db() as db:
            result = await db.execute(select(FormRequirementRuleModel))
            rules = result.scalars().all()

        idx: dict[str, dict[str, list[dict]]] = {}
        for r in rules:
            bucket = idx.setdefault(r.question_key, {})
            bucket.setdefault(r.question_value, []).append({
                "form_source": r.form_source,
                "form_number": r.form_number,
                "priority": r.priority,
                "note": r.note,
            })
        self._index = idx
        self._built = True

    def _match_sync(self, answers: dict[str, Any]) -> tuple[list[dict], set[tuple[str, str]]]:
        """
        CPU-bound rule matching — runs in a thread pool via anyio.to_thread.run_sync().

        Iterates the in-memory index without touching any async resources.
        Returns (matched_rules, seen_keys).
        """
        matched: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for q_key, q_val in answers.items():
            if not q_val:
                continue
            bucket = self._index.get(q_key, {})

            # Exact match
            for rule in bucket.get(q_val, []):
                key = (rule["form_source"], rule["form_number"])
                if key not in seen:
                    seen.add(key)
                    matched.append(dict(rule))

            # Wildcard match (any non-empty answer triggers)
            for rule in bucket.get("*", []):
                key = (rule["form_source"], rule["form_number"])
                if key not in seen:
                    seen.add(key)
                    matched.append(dict(rule))

        return matched, seen

    async def evaluate(
        self,
        answers: dict[str, Any],
        tax_year: int,
    ) -> list[dict]:
        """
        Evaluate answers against rules.

        Returns a sorted list of form matches:
            [{form_source, form_number, priority, note, form_details}]
        sorted required → likely → maybe.

        The CPU-bound rule-matching step is offloaded to a thread pool via
        anyio.to_thread.run_sync() so the async event loop is never blocked,
        even for large rule sets with thousands of questions.
        """
        import anyio

        if not self._built:
            await self.build()

        # Offload CPU-intensive rule matching to a worker thread
        matched, seen = await anyio.to_thread.run_sync(
            lambda: self._match_sync(answers)
        )

        # Attach form details
        async with get_db() as db:
            federal_result = await db.execute(select(FederalFormModel))
            federal_map = {f.form_number: f for f in federal_result.scalars().all()}

            state_code = answers.get("state_of_residence")
            state_map: dict[str, Any] = {}
            if state_code:
                state_result = await db.execute(
                    select(StateFormModel).where(StateFormModel.state_code == state_code)
                )
                state_map = {f.form_number: f for f in state_result.scalars().all()}

        for m in matched:
            if m["form_source"] == "federal":
                fd = federal_map.get(m["form_number"])
                m["form_details"] = _serialize_form(fd) if fd else None
            else:
                sd = state_map.get(m["form_number"])
                m["form_details"] = _serialize_state_form(sd) if sd else None

        # Add the primary state return if applicable and not already included
        state_code = answers.get("state_of_residence")
        if state_code and state_map:
            primary = next(iter(state_map.values()))
            key = ("state", primary.form_number)
            if key not in seen and primary.has_income_tax:
                matched.append({
                    "form_source": "state",
                    "form_number": primary.form_number,
                    "priority": "required",
                    "note": f"{primary.state_name} residents must file {primary.title}.",
                    "form_details": _serialize_state_form(primary),
                })

        ORDER = {"required": 0, "likely": 1, "maybe": 2}
        matched.sort(key=lambda x: ORDER.get(x["priority"], 3))
        return matched


def _serialize_form(f: FederalFormModel) -> dict:
    return {
        "id": f.id,
        "form_number": f.form_number,
        "title": f.title,
        "description": f.description,
        "category": f.category,
        "subcategory": f.subcategory,
        "who_files": f.who_files,
        "filing_methods": f.filing_methods,
        "irs_url": f.irs_url,
        "instructions_url": f.instructions_url,
    }


def _serialize_state_form(f: StateFormModel) -> dict:
    return {
        "id": f.id,
        "state_code": f.state_code,
        "state_name": f.state_name,
        "form_number": f.form_number,
        "title": f.title,
        "description": f.description,
        "has_income_tax": f.has_income_tax,
        "state_web_url": f.state_web_url,
        "filing_methods": f.filing_methods,
    }


# Module-level singleton — shared across requests
_rule_engine: Optional[RuleEngine] = None


def get_rule_engine() -> RuleEngine:
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = RuleEngine()
    return _rule_engine


def reset_rule_engine() -> None:
    """Reset the singleton (used in tests to force rebuild)."""
    global _rule_engine
    _rule_engine = None
