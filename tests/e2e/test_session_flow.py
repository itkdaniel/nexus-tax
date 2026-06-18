"""
End-to-end tests for the full questionnaire session flow.

These tests simulate a real taxpayer journey from session creation to form
identification, exercising the full stack: HTTP → router → engine → DB.

Scenarios:
  1. Individual single filer with W-2 income (most common case)
  2. Self-employed sole proprietor with home office
  3. Investor with capital gains + rental income
  4. Business (C corporation)
  5. Foreign income + accounts (FBAR triggers)
  6. Marketplace health insurance
  7. Early retirement withdrawal
  8. Session not found
  9. Concurrent session creation (isolation)
  10. Admin seed year
"""
from __future__ import annotations

import asyncio
import pytest


# ── 1. Individual single filer with W-2 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_w2_single_filer(client):
    """Full flow: W-2 single filer → 1040 required."""
    # Start session
    resp = await client.post("/v1/sessions", json={"tax_year": 2024})
    assert resp.status_code == 201
    sid = resp.json()["id"]

    # Answer questions
    answers = {
        "entity_type": "individual",
        "filing_status": "single",
        "has_w2": "yes",
        "health_insurance_source": "employer",
    }
    resp = await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": answers})
    assert resp.status_code == 200

    # Complete
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    assert resp.status_code == 200
    session = resp.json()

    assert session["status"] == "completed"
    form_numbers = [f["form_number"] for f in session["required_forms"]]
    assert "1040" in form_numbers
    assert "W-2" in form_numbers

    # Required forms come before likely/maybe
    priorities = [f["priority"] for f in session["required_forms"]]
    ORDER = {"required": 0, "likely": 1, "maybe": 2}
    ordered = [ORDER[p] for p in priorities]
    assert ordered == sorted(ordered)


# ── 2. Self-employed with home office ────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_self_employed_home_office(client):
    """Self-employed + home office → Schedule C, SE, 8829, 8995."""
    resp = await client.post("/v1/sessions", json={"tax_year": 2024, "entity_type": "individual"})
    sid = resp.json()["id"]

    await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
        "entity_type": "individual",
        "has_self_employment": "yes",
        "has_home_office": "yes",
    }})
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    forms = {f["form_number"] for f in resp.json()["required_forms"]}

    assert "Schedule C" in forms
    assert "Schedule SE" in forms
    assert "8829" in forms


# ── 3. Investor with capital gains + rental ───────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_investor_rental(client):
    """Capital gains + rental income → Schedule D, 8949, Schedule E."""
    resp = await client.post("/v1/sessions", json={"tax_year": 2024})
    sid = resp.json()["id"]

    await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
        "entity_type": "individual",
        "has_investment_income": "yes",
        "has_rental_income": "yes",
    }})
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    forms = {f["form_number"] for f in resp.json()["required_forms"]}

    assert "Schedule D" in forms
    assert "8949" in forms
    assert "1099-B" in forms
    assert "Schedule E" in forms


# ── 4. C corporation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_c_corporation(client):
    """C corporation → Form 1120 required."""
    resp = await client.post("/v1/sessions", json={"tax_year": 2024, "entity_type": "business"})
    sid = resp.json()["id"]

    await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
        "entity_type": "business",
        "business_entity_type": "c_corp",
    }})
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    forms = {f["form_number"] for f in resp.json()["required_forms"]}
    assert "1120" in forms


# ── 5. Foreign income + accounts ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_foreign_income_and_accounts(client):
    """Foreign income + foreign accounts → 2555, 1116, FBAR."""
    resp = await client.post("/v1/sessions", json={"tax_year": 2024})
    sid = resp.json()["id"]

    await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
        "entity_type": "individual",
        "has_foreign_income": "yes",
        "has_foreign_accounts": "yes",
    }})
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    forms = {f["form_number"] for f in resp.json()["required_forms"]}

    assert "2555" in forms
    assert "1116" in forms
    assert "FinCEN 114 (FBAR)" in forms


# ── 6. Marketplace health insurance ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_marketplace_insurance(client):
    """Marketplace insurance → 1095-A and 8962 required."""
    resp = await client.post("/v1/sessions", json={"tax_year": 2024})
    sid = resp.json()["id"]

    await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
        "entity_type": "individual",
        "health_insurance_source": "marketplace",
    }})
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    forms = {f["form_number"] for f in resp.json()["required_forms"]}
    assert "1095-A" in forms
    assert "8962" in forms


# ── 7. Early retirement withdrawal ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_early_retirement_withdrawal(client):
    """Early retirement withdrawal → 1099-R and 5329."""
    resp = await client.post("/v1/sessions", json={"tax_year": 2024})
    sid = resp.json()["id"]

    await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
        "entity_type": "individual",
        "has_retirement_income": "yes",
        "early_retirement_withdrawal": "yes",
    }})
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    forms = {f["form_number"] for f in resp.json()["required_forms"]}
    assert "1099-R" in forms
    assert "5329" in forms


# ── 8. Session not found ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_session_not_found(client):
    resp = await client.get("/v1/sessions/no-such-session-id")
    assert resp.status_code == 404
    assert resp.json()["code"] == "SESSION_NOT_FOUND"


# ── 9. Concurrent session creation (isolation) ───────────────────────────────

@pytest.mark.asyncio
async def test_e2e_concurrent_sessions(client):
    """Multiple concurrent sessions are fully isolated from each other."""
    async def create_and_complete(filing_status: str) -> dict:
        resp = await client.post("/v1/sessions", json={"tax_year": 2024})
        sid = resp.json()["id"]
        await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
            "entity_type": "individual",
            "filing_status": filing_status,
        }})
        resp = await client.post(f"/v1/sessions/{sid}/complete")
        return resp.json()

    results = await asyncio.gather(
        create_and_complete("single"),
        create_and_complete("mfj"),
        create_and_complete("hoh"),
    )

    # All completed successfully and are independent
    for session in results:
        assert session["status"] == "completed"

    # Sessions are different
    ids = [s["id"] for s in results]
    assert len(set(ids)) == 3


# ── 10. Tax calculation integration ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_tax_calculation_roundtrip(client):
    """Calculate tax for known income levels and verify mathematical properties."""
    test_cases = [
        {"income": 30_000, "status": "single",  "expected_deduction": 14600.0},
        {"income": 80_000, "status": "mfj",     "expected_deduction": 29200.0},
        {"income": 50_000, "status": "hoh",     "expected_deduction": 21900.0},
    ]
    for tc in test_cases:
        resp = await client.post("/v1/calculate", json={
            "income": tc["income"],
            "filing_status": tc["status"],
            "tax_year": 2024,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["standard_deduction"] == tc["expected_deduction"]
        assert data["taxable_income"] == tc["income"] - tc["expected_deduction"]
        assert data["federal_tax"] >= 0
        assert 0.0 <= data["effective_rate"] <= 0.37


# ── 11. Form lookup integration ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_form_lookup_and_detail_attached(client):
    """Completed session should have form_details attached for each form."""
    resp = await client.post("/v1/sessions", json={"tax_year": 2024})
    sid = resp.json()["id"]
    await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
        "entity_type": "individual",
        "has_w2": "yes",
    }})
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    forms = resp.json()["required_forms"]

    for form in forms:
        if form["form_source"] == "federal":
            if form["form_details"] is not None:
                assert "title" in form["form_details"]
                assert "description" in form["form_details"]


# ── 12. State CA with complete questionnaire ─────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_california_state_form(client):
    """California resident should get state form 540 added."""
    resp = await client.post("/v1/sessions", json={"tax_year": 2024})
    sid = resp.json()["id"]
    await client.patch(f"/v1/sessions/{sid}/answers", json={"answers": {
        "entity_type": "individual",
        "state_of_residence": "CA",
    }})
    resp = await client.post(f"/v1/sessions/{sid}/complete")
    forms = resp.json()["required_forms"]

    state_forms = [f for f in forms if f["form_source"] == "state"]
    assert len(state_forms) >= 1
    assert state_forms[0]["form_number"] == "540"
    assert state_forms[0]["priority"] == "required"
