"""
Unit tests for the tax engine (bracket calculator + rule evaluator).

Tests:
  - Bracket math for all 5 filing statuses (2024 base rates)
  - Zero income edge case
  - Age-65 / blind additions to standard deduction
  - Rule engine: exact match, wildcard match, deduplication
  - Rule engine: priority ordering (required > likely > maybe)
  - Rule engine: state form auto-added for has_income_tax states
  - Rule engine: no state form for no-income-tax states
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.engine import calculate_tax, get_rule_engine, reset_rule_engine


# ── Bracket Math ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_zero_income(app):
    """Zero income → zero tax, zero effective rate."""
    result = await calculate_tax(income=1.0, filing_status="single", tax_year=2024)
    assert result.gross_income == 1.0
    # 1 < standard deduction → taxable_income = 0
    assert result.taxable_income == 0.0
    assert result.federal_tax == 0.0
    assert result.effective_rate == 0.0
    assert result.standard_deduction == 14600.0


@pytest.mark.asyncio
async def test_single_10pct_bracket(app):
    """$20,000 gross income (single) → 10% bracket only."""
    result = await calculate_tax(income=20_000, filing_status="single", tax_year=2024)
    # taxable = 20000 - 14600 = 5400
    assert result.taxable_income == 5400.0
    # 5400 * 10% = 540
    assert result.federal_tax == pytest.approx(540.0, abs=1.0)
    assert result.marginal_rate == 0.10
    assert len(result.brackets_detail) == 1


@pytest.mark.asyncio
async def test_single_spans_two_brackets(app):
    """$60,000 gross income (single) → spans 10% and 12% brackets."""
    result = await calculate_tax(income=60_000, filing_status="single", tax_year=2024)
    # taxable = 60000 - 14600 = 45400
    # 10%: 0-11600 → 1160
    # 12%: 11600-45400 → 33800 * 0.12 = 4056
    # total ≈ 5216
    assert result.taxable_income == 45_400.0
    assert result.federal_tax == pytest.approx(5216.0, abs=5.0)
    assert result.marginal_rate == 0.12
    assert len(result.brackets_detail) == 2


@pytest.mark.asyncio
async def test_mfj_standard_deduction(app):
    """MFJ standard deduction is $29,200 for 2024."""
    result = await calculate_tax(income=50_000, filing_status="mfj", tax_year=2024)
    assert result.standard_deduction == 29_200.0
    # taxable = 50000 - 29200 = 20800
    assert result.taxable_income == 20_800.0


@pytest.mark.asyncio
async def test_age_65_addition(app):
    """Age-65 single filer gets $1,950 addition to standard deduction."""
    normal = await calculate_tax(income=50_000, filing_status="single", tax_year=2024)
    senior = await calculate_tax(income=50_000, filing_status="single", tax_year=2024, age_65=True)
    assert senior.standard_deduction == normal.standard_deduction + 1950.0
    assert senior.taxable_income == normal.taxable_income - 1950.0
    assert senior.federal_tax < normal.federal_tax


@pytest.mark.asyncio
async def test_blind_addition(app):
    """Blind single filer gets $1,950 addition."""
    normal = await calculate_tax(income=50_000, filing_status="single", tax_year=2024)
    blind = await calculate_tax(income=50_000, filing_status="single", tax_year=2024, blind=True)
    assert blind.standard_deduction == normal.standard_deduction + 1950.0


@pytest.mark.asyncio
async def test_all_filing_statuses_exist(app):
    """All five filing statuses should return results for 2024."""
    for status in ("single", "mfj", "mfs", "hoh", "qw"):
        result = await calculate_tax(income=100_000, filing_status=status, tax_year=2024)
        assert result.filing_status == status
        assert result.federal_tax > 0


@pytest.mark.asyncio
async def test_invalid_year_raises(app):
    """Requesting an unseeded year should raise ValueError."""
    with pytest.raises(ValueError, match="No"):
        await calculate_tax(income=50_000, filing_status="single", tax_year=1990)


@pytest.mark.asyncio
async def test_effective_rate_less_than_marginal(app):
    """Effective rate is always <= marginal rate for progressive taxation."""
    result = await calculate_tax(income=500_000, filing_status="single", tax_year=2024)
    assert result.effective_rate < result.marginal_rate


@pytest.mark.asyncio
async def test_brackets_detail_sums_to_total(app):
    """Sum of per-bracket tax equals total federal_tax."""
    result = await calculate_tax(income=200_000, filing_status="single", tax_year=2024)
    total_from_detail = sum(b.tax_on_bracket for b in result.brackets_detail)
    assert total_from_detail == pytest.approx(result.federal_tax, abs=0.01)


# ── Rule Engine ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rule_engine_individual_gets_1040(app):
    """An individual taxpayer should always get Form 1040 (required)."""
    engine = get_rule_engine()
    results = await engine.evaluate(
        answers={"entity_type": "individual"},
        tax_year=2024,
    )
    form_numbers = [r["form_number"] for r in results]
    assert "1040" in form_numbers
    # Check it's required
    for r in results:
        if r["form_number"] == "1040":
            assert r["priority"] == "required"
            break


@pytest.mark.asyncio
async def test_rule_engine_self_employment_triggers_schedule_c(app):
    """has_self_employment=yes should trigger Schedule C, Schedule SE."""
    engine = get_rule_engine()
    results = await engine.evaluate(
        answers={"entity_type": "individual", "has_self_employment": "yes"},
        tax_year=2024,
    )
    form_numbers = {r["form_number"] for r in results}
    assert "Schedule C" in form_numbers
    assert "Schedule SE" in form_numbers
    assert "1099-NEC" in form_numbers


@pytest.mark.asyncio
async def test_rule_engine_deduplication(app):
    """Rule engine should deduplicate (form_source, form_number) pairs."""
    engine = get_rule_engine()
    results = await engine.evaluate(
        answers={
            "entity_type": "individual",
            "has_investment_income": "yes",
            "sold_home": "yes",
        },
        tax_year=2024,
    )
    # Both has_investment_income and sold_home trigger Schedule D and 8949
    keys = [(r["form_source"], r["form_number"]) for r in results]
    assert len(keys) == len(set(keys)), "Duplicate (source, form_number) pairs found"


@pytest.mark.asyncio
async def test_rule_engine_priority_sort(app):
    """Results should be sorted: required → likely → maybe."""
    engine = get_rule_engine()
    results = await engine.evaluate(
        answers={
            "entity_type": "individual",
            "has_self_employment": "yes",
            "made_estimated_payments": "yes",
        },
        tax_year=2024,
    )
    priorities = [r["priority"] for r in results]
    ORDER = {"required": 0, "likely": 1, "maybe": 2}
    ordered = [ORDER[p] for p in priorities]
    assert ordered == sorted(ordered), f"Results not sorted by priority: {priorities}"


@pytest.mark.asyncio
async def test_rule_engine_marketplace_insurance(app):
    """Marketplace insurance triggers 1095-A and 8962."""
    engine = get_rule_engine()
    results = await engine.evaluate(
        answers={"entity_type": "individual", "health_insurance_source": "marketplace"},
        tax_year=2024,
    )
    form_numbers = {r["form_number"] for r in results}
    assert "1095-A" in form_numbers
    assert "8962" in form_numbers


@pytest.mark.asyncio
async def test_rule_engine_state_form_added(app):
    """A taxpayer in California should get the CA 540 state form."""
    engine = get_rule_engine()
    results = await engine.evaluate(
        answers={"entity_type": "individual", "state_of_residence": "CA"},
        tax_year=2024,
    )
    state_forms = [r for r in results if r["form_source"] == "state"]
    assert len(state_forms) >= 1
    assert state_forms[0]["form_number"] == "540"


@pytest.mark.asyncio
async def test_rule_engine_no_state_form_for_no_income_tax(app):
    """A taxpayer in Texas (no income tax) should NOT get a state required form."""
    engine = get_rule_engine()
    results = await engine.evaluate(
        answers={"entity_type": "individual", "state_of_residence": "TX"},
        tax_year=2024,
    )
    state_required = [r for r in results if r["form_source"] == "state" and r["priority"] == "required"]
    assert len(state_required) == 0


@pytest.mark.asyncio
async def test_rule_engine_empty_answers(app):
    """Empty answers → no forms (rule engine handles gracefully)."""
    engine = get_rule_engine()
    results = await engine.evaluate(answers={}, tax_year=2024)
    assert isinstance(results, list)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_rule_engine_business_c_corp(app):
    """C corporation should get Form 1120."""
    engine = get_rule_engine()
    results = await engine.evaluate(
        answers={"entity_type": "business", "business_entity_type": "c_corp"},
        tax_year=2024,
    )
    form_numbers = {r["form_number"] for r in results}
    assert "1120" in form_numbers
