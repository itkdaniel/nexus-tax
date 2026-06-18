"""
Regression / contract tests for nexus-tax API.

These tests act as a safety net against breaking changes to the API surface.
They snapshot expected response shapes and key field values.

Contract areas tested:
  - /health response shape
  - /info service name and endpoint list
  - GET /v1/forms/federal response shape
  - GET /v1/rates/2024 response shape
  - GET /v1/questions response shape
  - POST /v1/sessions → GET shape
  - POST /v1/calculate response shape
  - Error envelope shape (404, 422)
"""
from __future__ import annotations

import pytest
import pytest_asyncio


# ── /health ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_contract(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "nexus-tax"
    assert "version" in data
    assert "uptime" in data
    assert isinstance(data["uptime"], (int, float))


# ── /info ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_info_contract(client):
    resp = await client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "nexus-tax"
    assert data["port"] == 8003
    assert isinstance(data["endpoints"], list)
    assert len(data["endpoints"]) >= 14
    # Verify endpoint shape
    ep = data["endpoints"][0]
    assert "method" in ep
    assert "path" in ep
    assert "auth" in ep
    assert "description" in ep


# ── Federal forms ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_federal_forms_list_contract(client):
    resp = await client.get("/v1/tax/forms/federal")
    assert resp.status_code == 200
    forms = resp.json()
    assert isinstance(forms, list)
    assert len(forms) >= 40

    # Check a well-known form exists
    form_numbers = {f["form_number"] for f in forms}
    assert "1040" in form_numbers
    assert "Schedule C" in form_numbers

    # Shape contract
    form = forms[0]
    required_keys = {"id", "form_number", "title", "description", "category", "who_files", "filing_methods", "is_active", "sort_order"}
    assert required_keys.issubset(form.keys())


@pytest.mark.asyncio
async def test_federal_form_by_number_contract(client):
    resp = await client.get("/v1/tax/forms/federal/1040")
    assert resp.status_code == 200
    form = resp.json()
    assert form["form_number"] == "1040"
    assert form["category"] == "individual"
    assert isinstance(form["filing_methods"], list)


@pytest.mark.asyncio
async def test_federal_form_not_found(client):
    resp = await client.get("/v1/tax/forms/federal/NONEXISTENT-FORM-XYZ")
    assert resp.status_code == 404
    data = resp.json()
    # Error envelope contract
    assert "error" in data
    assert "code" in data
    assert data["code"] == "FORM_NOT_FOUND"


@pytest.mark.asyncio
async def test_state_forms_list_contract(client):
    resp = await client.get("/v1/tax/forms/state")
    assert resp.status_code == 200
    forms = resp.json()
    assert isinstance(forms, list)
    assert len(forms) >= 51  # 50 states + DC
    state_codes = {f["state_code"] for f in forms}
    assert "CA" in state_codes
    assert "TX" in state_codes
    assert "DC" in state_codes


@pytest.mark.asyncio
async def test_state_forms_by_code_contract(client):
    resp = await client.get("/v1/tax/forms/state/CA")
    assert resp.status_code == 200
    forms = resp.json()
    assert len(forms) == 1
    assert forms[0]["state_code"] == "CA"
    assert forms[0]["form_number"] == "540"
    assert forms[0]["has_income_tax"] is True


@pytest.mark.asyncio
async def test_state_forms_no_income_tax_state(client):
    resp = await client.get("/v1/tax/forms/state/TX")
    assert resp.status_code == 200
    forms = resp.json()
    assert forms[0]["has_income_tax"] is False


# ── Rates ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_bundle_contract(client):
    resp = await client.get("/v1/tax/rates/2024")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tax_year"] == 2024
    assert "brackets" in data
    assert "standard_deductions" in data
    assert "special_rates" in data
    # 5 statuses × 7 brackets = 35
    assert len(data["brackets"]) == 35
    # 5 statuses × 1 deduction row = 5
    assert len(data["standard_deductions"]) == 5


@pytest.mark.asyncio
async def test_rate_bundle_year_not_found(client):
    resp = await client.get("/v1/tax/rates/1985")
    assert resp.status_code == 404
    assert resp.json()["code"] == "YEAR_NOT_FOUND"


@pytest.mark.asyncio
async def test_brackets_filtered_by_status(client):
    resp = await client.get("/v1/tax/rates/2024/brackets?filing_status=single")
    assert resp.status_code == 200
    brackets = resp.json()
    assert len(brackets) == 7
    assert all(b["filing_status"] == "single" for b in brackets)
    # Brackets ordered ascending by income_from
    from_values = [b["income_from"] for b in brackets]
    assert from_values == sorted(from_values)


# ── Calculate ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calculate_contract(client):
    resp = await client.post(
        "/v1/tax/calculate",
        json={"income": 75_000, "filing_status": "single", "tax_year": 2024},
    )
    assert resp.status_code == 200
    data = resp.json()
    required_keys = {
        "tax_year", "filing_status", "gross_income", "standard_deduction",
        "taxable_income", "federal_tax", "effective_rate", "marginal_rate",
        "brackets_detail",
    }
    assert required_keys.issubset(data.keys())
    assert data["tax_year"] == 2024
    assert data["filing_status"] == "single"
    assert data["gross_income"] == 75_000.0
    assert data["standard_deduction"] == 14_600.0
    assert data["federal_tax"] > 0
    assert isinstance(data["brackets_detail"], list)
    assert len(data["brackets_detail"]) > 0
    bd = data["brackets_detail"][0]
    assert {"rate", "income_from", "income_in_bracket", "tax_on_bracket"}.issubset(bd.keys())


@pytest.mark.asyncio
async def test_calculate_invalid_status_contract(client):
    resp = await client.post(
        "/v1/tax/calculate",
        json={"income": 50_000, "filing_status": "married", "tax_year": 2024},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert "code" in data


# ── Questions ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_questions_list_contract(client):
    resp = await client.get("/v1/tax/questions")
    assert resp.status_code == 200
    questions = resp.json()
    assert isinstance(questions, list)
    assert len(questions) >= 30  # ~38 questions seeded

    q = questions[0]
    required_keys = {
        "id", "question_key", "category", "question_text", "input_type",
        "is_required", "sort_order", "applies_to_individual", "applies_to_business",
    }
    assert required_keys.issubset(q.keys())

    # Ordered by sort_order
    orders = [q["sort_order"] for q in questions]
    assert orders == sorted(orders)


@pytest.mark.asyncio
async def test_questions_first_is_entity_type(client):
    resp = await client.get("/v1/tax/questions")
    assert resp.status_code == 200
    first = resp.json()[0]
    assert first["question_key"] == "entity_type"


# ── Sessions ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_lifecycle_contract(client):
    # Create
    resp = await client.post("/v1/tax/sessions", json={"tax_year": 2024, "entity_type": "individual"})
    assert resp.status_code == 201
    session = resp.json()
    assert "id" in session
    assert session["status"] == "in_progress"
    assert session["tax_year"] == 2024
    assert session["answers"] == {}
    assert session["required_forms"] is None
    sid = session["id"]

    # Get
    resp = await client.get(f"/v1/tax/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sid

    # Update answers
    resp = await client.patch(f"/v1/tax/sessions/{sid}/answers", json={"answers": {"entity_type": "individual", "has_w2": "yes"}})
    assert resp.status_code == 200
    assert resp.json()["answers"]["entity_type"] == "individual"

    # Complete
    resp = await client.post(f"/v1/tax/sessions/{sid}/complete")
    assert resp.status_code == 200
    completed = resp.json()
    assert completed["status"] == "completed"
    assert completed["required_forms"] is not None
    assert isinstance(completed["required_forms"], list)
    assert completed["completed_at"] is not None


@pytest.mark.asyncio
async def test_session_not_found(client):
    resp = await client.get("/v1/tax/sessions/nonexistent-id-xyz")
    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "SESSION_NOT_FOUND"


# ── Periods ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_periods_list_contract(client):
    resp = await client.get("/v1/tax/periods")
    assert resp.status_code == 200
    periods = resp.json()
    assert isinstance(periods, list)
    assert len(periods) >= 1
    p = periods[0]
    assert "tax_year" in p
    assert "filing_deadline" in p
    assert "extension_deadline" in p
    assert "status" in p
    assert p["tax_year"] == 2024


# ── Admin ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_seed_requires_auth(client):
    resp = await client.post("/v1/tax/admin/seed-year", json={"tax_year": 2024})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_seed_with_auth(admin_client):
    resp = await admin_client.post("/v1/tax/admin/seed-year", json={"tax_year": 2025})
    assert resp.status_code == 200
    assert "seeded successfully" in resp.json()["message"]
