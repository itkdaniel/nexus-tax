# nexus-tax Developer Guide

Standalone FastAPI microservice that powers the **Tax Assistant** in the
NexusConsult portfolio.  It runs on **port 8003** and exposes a fully
versioned REST API under `/v1/tax/`.

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/itkdaniel/nexus-tax.git
cd nexus-tax

# 2. Install Python deps (Python 3.11+)
pip install -r requirements.txt         # production
pip install -r requirements-dev.txt     # + test tools

# 3. Set environment vars (see .env.example)
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/nexus_tax"
export JWT_SECRET="your-secret-here"

# 4. Run database migrations (production)
alembic upgrade head

# 5. Start the service
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

Interactive docs are available at `http://localhost:8003/docs`.

---

## Development (SQLite in-memory, no migrations needed)

```bash
# Run with auto-create tables + seed (debug=true)
DEBUG=true uvicorn app.main:app --port 8003 --reload
```

---

## Running tests

```bash
# All tests
pytest

# Specific suites
pytest tests/unit/           # pure-Python engine tests (fast)
pytest tests/regression/     # HTTP contract tests
pytest tests/e2e/            # end-to-end session flows
pytest tests/bdd/            # Gherkin scenarios
pytest tests/property/       # Hypothesis property tests

# With coverage
pytest --cov=app --cov-report=term-missing
```

---

## API reference

All routes live under `/v1/tax/`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | — | Liveness probe |
| GET | `/info` | — | Service metadata |
| GET | `/v1/tax/forms/federal` | — | List federal forms |
| GET | `/v1/tax/forms/federal/{form_number}` | — | Single federal form |
| GET | `/v1/tax/forms/state` | — | List all state forms |
| GET | `/v1/tax/forms/state/{state_code}` | — | State forms by state code |
| GET | `/v1/tax/rates/{year}` | — | Full rate bundle |
| GET | `/v1/tax/rates/{year}/brackets` | — | Tax brackets |
| GET | `/v1/tax/rates/{year}/deductions` | — | Standard deductions |
| GET | `/v1/tax/rates/{year}/special` | — | Special tax rates |
| POST | `/v1/tax/calculate` | — | Calculate federal income tax |
| GET | `/v1/tax/questions` | — | Questionnaire questions |
| POST | `/v1/tax/sessions` | — | Start questionnaire session |
| GET | `/v1/tax/sessions/{id}` | — | Get session state |
| PATCH | `/v1/tax/sessions/{id}/answers` | — | Save answers progressively |
| POST | `/v1/tax/sessions/{id}/complete` | — | Compute required forms |
| GET | `/v1/tax/sessions/{id}/required-forms` | — | Fetch required forms |
| GET | `/v1/tax/periods` | — | List tax periods |
| POST | `/v1/tax/admin/seed-year` | ✓ admin | Manual seed trigger |

---

## Architecture

```
app/
├── main.py          Application factory (create_app)
├── config.py        Pydantic-settings typed config
├── auth.py          HMAC-SHA256 JWT (require_auth / require_admin)
├── database.py      Async SQLAlchemy engine factory
├── engine.py        BracketCalculator + O(q) RuleEngine
├── models.py        SQLAlchemy ORM + Pydantic schemas
├── seed.py          80+ federal forms, 52 state forms, brackets, rules
├── scheduler.py     APScheduler: annual seed on Jan 1 00:05 UTC
└── routers/
    ├── forms.py     Federal + state form lookup
    ├── rates.py     Brackets, deductions, special rates, calculator
    ├── questions.py Questionnaire catalogue
    ├── sessions.py  Session lifecycle (create / answer / complete)
    └── admin.py     Periods list + seed-year trigger
```

### Key design decisions

- **Factory pattern** — `create_app(settings=None)` accepts injected settings,
  enabling fully isolated in-memory SQLite tests.
- **asyncio.gather** — session creation concurrently fetches the tax period and
  question catalogue; zero added latency.
- **O(q) rule engine** — built at startup into a lookup dict
  `{question_key: {value: [rules]}}`.  Evaluation is a single pass over answers.
- **Annual scheduler** — APScheduler CronTrigger fires at 00:05 UTC Jan 1,
  seeds the new year, closes the prior-2 year, resets the rule engine.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | SQLite in-memory | Async SQLAlchemy URL |
| `JWT_SECRET` | `change-me-in-production` | HMAC signing secret |
| `PORT` | `8003` | Listen port |
| `DEBUG` | `false` | Enables auto-table-create + SQLite fallback |
| `DEFAULT_TAX_YEAR` | `2024` | Year to seed at startup |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |

---

## Docker

```bash
# Build
docker build -t nexus-tax .

# Run (production)
docker run -p 8003:8003 \
  -e DATABASE_URL="postgresql+asyncpg://..." \
  -e JWT_SECRET="..." \
  nexus-tax

# Docker Compose (dev)
docker compose up
```
