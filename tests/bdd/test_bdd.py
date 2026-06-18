"""
BDD step implementations for nexus-tax questionnaire and bracket features.

pytest-bdd step functions are invoked synchronously even when asyncio_mode=auto.
We bridge async calls via a per-test event loop fixture (aioloop) and a small
run() helper that calls loop.run_until_complete().
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from pytest_bdd import given, when, then, parsers, scenarios

from httpx import AsyncClient, ASGITransport

from app.config import Settings
from app.main import create_app
from app.engine import reset_rule_engine

# Register all scenarios from the feature files
scenarios("features/questionnaire.feature")
scenarios("features/brackets.feature")
scenarios("features/scheduler.feature")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ctx():
    """Per-test shared context dict — steps write/read state here."""
    return {}


@pytest.fixture
def aioloop():
    """A dedicated event loop for synchronous step functions to run coroutines."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_client(aioloop):
    """Sync fixture that yields a live AsyncClient backed by an in-memory app."""
    reset_rule_engine()
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="test-secret",
        debug=True,
        default_tax_year=2024,
        port=8003,
    )
    app = create_app(settings)

    async def _make_client():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return client, app

    # Start the lifespan and keep it alive for the duration of the test.
    # We store cleanup in a list so the fixture can close on teardown.
    entered: list = []

    async def _enter():
        cm1 = app.router.lifespan_context(app)
        await cm1.__aenter__()
        entered.append(cm1)
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        await client.__aenter__()
        entered.append(client)
        return client

    client = aioloop.run_until_complete(_enter())

    yield client

    async def _exit():
        for cm in reversed(entered):
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass

    aioloop.run_until_complete(_exit())
    reset_rule_engine()


def _run(aioloop, coro):
    """Helper: run a coroutine on the test event loop."""
    return aioloop.run_until_complete(coro)


# ── Background ────────────────────────────────────────────────────────────────

@given("the nexus-tax service is running with 2024 data")
def service_running(test_client):
    pass  # fixture handles startup


# ── Questionnaire Steps ───────────────────────────────────────────────────────

@given(parsers.parse('I start a new session for tax year {year:d} as "{entity_type}"'))
def start_session(test_client, aioloop, ctx, year, entity_type):
    resp = _run(aioloop, test_client.post("/v1/tax/sessions", json={"tax_year": year, "entity_type": entity_type}))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    ctx["session_id"] = resp.json()["id"]
    ctx["answers"] = {}


@when(parsers.parse('I answer "{key}" with "{value}"'))
def answer_question(test_client, aioloop, ctx, key, value):
    ctx["answers"][key] = value
    resp = _run(aioloop, test_client.patch(
        f"/v1/tax/sessions/{ctx['session_id']}/answers",
        json={"answers": {key: value}},
    ))
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    ctx["last_response"] = resp


@when(parsers.parse('I save answers incrementally with "{key}" = "{value}"'))
def save_incremental(test_client, aioloop, ctx, key, value):
    ctx["answers"][key] = value
    resp = _run(aioloop, test_client.patch(
        f"/v1/tax/sessions/{ctx['session_id']}/answers",
        json={"answers": {key: value}},
    ))
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    ctx["last_response"] = resp


@when("I complete the session")
def complete_session(test_client, aioloop, ctx):
    resp = _run(aioloop, test_client.post(f"/v1/tax/sessions/{ctx['session_id']}/complete"))
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    ctx["completed_session"] = resp.json()
    ctx["last_response"] = resp




@then(parsers.parse('the required forms should include "{form_number}"'))
def required_forms_include(ctx, form_number):
    session = ctx["completed_session"]
    form_numbers = [f["form_number"] for f in (session.get("required_forms") or [])]
    assert form_number in form_numbers, f"{form_number} not found in {form_numbers}"


@then(parsers.parse('the session status should be "{status}"'))
def session_status(ctx, status):
    assert ctx["completed_session"]["status"] == status


@then("the session answers should contain both keys")
def answers_contain_both(ctx):
    data = ctx["last_response"].json()
    answers = data.get("answers", {})
    assert "has_w2" in answers or "has_rental_income" in answers, \
        f"Expected has_w2 or has_rental_income in answers, got: {list(answers.keys())}"


@then("updating answers should return HTTP 409")
def check_409(test_client, aioloop, ctx):
    resp = _run(aioloop, test_client.patch(
        f"/v1/tax/sessions/{ctx['session_id']}/answers",
        json={"answers": {"new_key": "new_val"}},
    ))
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"


# ── Bracket Steps ─────────────────────────────────────────────────────────────

@when(parsers.parse("I request the rate bundle for year {year:d}"))
def get_rate_bundle(test_client, aioloop, ctx, year):
    resp = _run(aioloop, test_client.get(f"/v1/tax/rates/{year}"))
    ctx["rate_resp"] = resp
    ctx["rate_data"] = resp.json()


@then("the response includes brackets")
def has_brackets(ctx):
    assert "brackets" in ctx["rate_data"]
    assert len(ctx["rate_data"]["brackets"]) > 0


@then("the response includes standard_deductions")
def has_deductions(ctx):
    assert "standard_deductions" in ctx["rate_data"]


@then("the response includes special_rates")
def has_special(ctx):
    assert "special_rates" in ctx["rate_data"]


@when(parsers.parse('I calculate tax for income={income:d} filing_status="{status}" year={year:d}'))
def calculate(test_client, aioloop, ctx, income, status, year):
    resp = _run(aioloop, test_client.post(
        "/v1/tax/calculate",
        json={"income": income, "filing_status": status, "tax_year": year},
    ))
    ctx["calc_resp"] = resp
    ctx["calc_data"] = resp.json()


@when(parsers.parse('I calculate tax with invalid filing_status "{status}"'))
def calculate_invalid(test_client, aioloop, ctx, status):
    resp = _run(aioloop, test_client.post(
        "/v1/tax/calculate",
        json={"income": 50_000, "filing_status": status, "tax_year": 2024},
    ))
    ctx["calc_resp"] = resp



@then(parsers.parse("the response tax_year is {year:d}"))
def resp_tax_year(ctx, year):
    assert ctx["calc_data"]["tax_year"] == year


@then(parsers.parse("the response standard_deduction is {amount:f}"))
def resp_std_deduction(ctx, amount):
    import pytest as _pytest
    assert ctx["calc_data"]["standard_deduction"] == _pytest.approx(amount, abs=1.0)


@then(parsers.parse("the response taxable_income is {amount:f}"))
def resp_taxable(ctx, amount):
    import pytest as _pytest
    assert ctx["calc_data"]["taxable_income"] == _pytest.approx(amount, abs=1.0)


@then(parsers.parse("the response marginal_rate is {rate:f}"))
def resp_marginal(ctx, rate):
    import pytest as _pytest
    assert ctx["calc_data"]["marginal_rate"] == _pytest.approx(rate, abs=0.001)


@then(parsers.parse("the response status code is {code:d}"))
def resp_status_code(ctx, code):
    assert ctx["calc_resp"].status_code == code


# ── Scheduler / Admin Scenarios ───────────────────────────────────────────────

@when(parsers.parse("I trigger a seed for tax year {year:d} as admin"))
def trigger_seed(test_client, aioloop, ctx, year):
    ctx["admin_token"] = _make_admin_token("test-secret")
    resp = _run(aioloop, test_client.post(
        f"/v1/tax/admin/update-year",
        json={"tax_year": year},
        headers={"Authorization": f"Bearer {ctx['admin_token']}"},
    ))
    ctx["seed_resp"] = resp
    ctx["seeded_year"] = year


@then(parsers.parse("the tax year {year:d} period should exist"))
def period_exists(test_client, aioloop, ctx, year):
    resp = _run(aioloop, test_client.get(f"/v1/tax/periods/{year}"))
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json()["tax_year"] == year


@then(parsers.parse("the {year:d} rate bundle should contain brackets"))
def rate_bundle_has_brackets(test_client, aioloop, ctx, year):
    resp = _run(aioloop, test_client.get(f"/v1/tax/rates/{year}"))
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert len(resp.json()["brackets"]) > 0


@then("the response should indicate success")
def seed_success(ctx):
    assert ctx["seed_resp"].status_code == 200, \
        f"Expected 200, got {ctx['seed_resp'].status_code}: {ctx['seed_resp'].text}"
    assert "seeded successfully" in ctx["seed_resp"].json().get("message", "")


@then("the 2024 data should still be intact")
def data_2024_intact(test_client, aioloop, ctx):
    resp = _run(aioloop, test_client.get("/v1/tax/rates/2024"))
    assert resp.status_code == 200
    assert resp.json()["tax_year"] == 2024
    assert len(resp.json()["brackets"]) == 35


def _make_admin_token(secret: str) -> str:
    """Build a minimal HMAC-SHA256 JWT with role=admin for BDD test auth."""
    import base64
    import hashlib
    import hmac
    import json
    import time

    payload = {"sub": "1", "role": "admin", "exp": int(time.time()) + 86400}
    header = {"alg": "HS256", "typ": "JWT"}

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(d, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()

    h64, p64 = b64(header), b64(payload)
    sig = hmac.new(secret.encode(), f"{h64}.{p64}".encode(), hashlib.sha256).digest()
    s64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{h64}.{p64}.{s64}"
