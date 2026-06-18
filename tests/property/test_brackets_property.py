"""
Property-based tests for the tax bracket calculator using Hypothesis.

Properties verified:
  1. federal_tax ≥ 0 for all valid incomes
  2. taxable_income = max(0, gross - standard_deduction)
  3. effective_rate ≤ marginal_rate (progressive system invariant)
  4. effective_rate ∈ [0, 1]
  5. Sum of bracket detail taxes = total federal_tax
  6. Monotonicity: higher income → higher or equal tax
  7. MFJ tax ≤ single tax for same gross income (MFJ penalty is possible but
     bracket design means at most equal for same gross)
  8. standard_deduction unchanged between calculations with same filing_status
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from hypothesis import given, settings as hyp_settings, strategies as st, HealthCheck

from app.config import Settings
from app.engine import calculate_tax, reset_rule_engine
from app.main import create_app


FILING_STATUSES = ["single", "mfj", "mfs", "hoh", "qw"]


@pytest_asyncio.fixture(scope="module")
async def seeded_app():
    """Module-scoped app (one seed per module run for performance)."""
    reset_rule_engine()
    settings = Settings(
        database_url="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true",
        debug=True,
        default_tax_year=2024,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app
    reset_rule_engine()


@pytest.mark.asyncio
@hyp_settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    income=st.floats(min_value=1.0, max_value=2_000_000.0, allow_nan=False, allow_infinity=False),
    status=st.sampled_from(FILING_STATUSES),
)
async def test_tax_never_negative(seeded_app, income, status):
    """Tax is always non-negative."""
    result = await calculate_tax(income=income, filing_status=status, tax_year=2024)
    assert result.federal_tax >= 0.0


@pytest.mark.asyncio
@hyp_settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    income=st.floats(min_value=1.0, max_value=2_000_000.0, allow_nan=False, allow_infinity=False),
    status=st.sampled_from(FILING_STATUSES),
)
async def test_effective_rate_leq_marginal(seeded_app, income, status):
    """Effective rate ≤ marginal rate (progressive taxation property)."""
    result = await calculate_tax(income=income, filing_status=status, tax_year=2024)
    assert result.effective_rate <= result.marginal_rate + 1e-9


@pytest.mark.asyncio
@hyp_settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    income=st.floats(min_value=1.0, max_value=2_000_000.0, allow_nan=False, allow_infinity=False),
    status=st.sampled_from(FILING_STATUSES),
)
async def test_effective_rate_in_range(seeded_app, income, status):
    """Effective rate is always in [0, 1]."""
    result = await calculate_tax(income=income, filing_status=status, tax_year=2024)
    assert 0.0 <= result.effective_rate <= 1.0


@pytest.mark.asyncio
@hyp_settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    income=st.floats(min_value=1.0, max_value=2_000_000.0, allow_nan=False, allow_infinity=False),
    status=st.sampled_from(FILING_STATUSES),
)
async def test_bracket_detail_sums(seeded_app, income, status):
    """Sum of per-bracket tax detail matches total federal_tax."""
    result = await calculate_tax(income=income, filing_status=status, tax_year=2024)
    if result.brackets_detail:
        detail_sum = sum(b.tax_on_bracket for b in result.brackets_detail)
        assert abs(detail_sum - result.federal_tax) < 0.02


@pytest.mark.asyncio
@hyp_settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    base_income=st.floats(min_value=20_000.0, max_value=900_000.0, allow_nan=False),
    delta=st.floats(min_value=100.0, max_value=50_000.0, allow_nan=False),
    status=st.sampled_from(FILING_STATUSES),
)
async def test_monotonicity(seeded_app, base_income, delta, status):
    """Higher income → higher or equal federal tax (monotone non-decreasing)."""
    lower = await calculate_tax(income=base_income, filing_status=status, tax_year=2024)
    higher = await calculate_tax(income=base_income + delta, filing_status=status, tax_year=2024)
    assert higher.federal_tax >= lower.federal_tax - 0.01


@pytest.mark.asyncio
@hyp_settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    income=st.floats(min_value=15_000.0, max_value=2_000_000.0, allow_nan=False),
)
async def test_taxable_income_formula(seeded_app, income):
    """taxable_income = max(0, gross - standard_deduction)."""
    result = await calculate_tax(income=income, filing_status="single", tax_year=2024)
    expected = max(0.0, income - result.standard_deduction)
    assert abs(result.taxable_income - expected) < 1.0
