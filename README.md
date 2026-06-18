# nexus-tax

Standalone tax assistant microservice for the NexusConsult portfolio.

**Port:** 8003 | **Source:** [github.com/itkdaniel/nexus-tax](https://github.com/itkdaniel/nexus-tax)

## Features

- **80+ Federal forms** — 1040 family, schedules, informational forms, business returns
- **51 State entries** — all 50 states + DC with income-tax status
- **Tax brackets** — 5 filing statuses × 7 tiers, inflation-adjusted per year (~3%)
- **Standard deductions** — base + age-65 + blind additions
- **Special tax rates** — FICA, SE, NIIT, AMT, cap-gains, kiddie tax
- **Questionnaire engine** — 38 questions with dependency chains; O(q) rule evaluation
- **Annual scheduler** — APScheduler seeds new year on Jan 1, closes prior-2 year
- **Tax calculator** — progressive bracket calculation with per-band breakdown

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | — | Liveness probe |
| GET | `/info` | — | Service metadata |
| GET | `/v1/tax/forms/federal` | — | List federal forms (`?category=`) |
| GET | `/v1/tax/forms/federal/{form_number}` | — | Get federal form by number |
| GET | `/v1/tax/forms/state` | — | List all state forms (`?code=CA`) |
| GET | `/v1/tax/forms/state/{state_code}` | — | Get forms for a state |
| GET | `/v1/tax/rates/{year}` | — | Full rate bundle (brackets + deductions + special) |
| GET | `/v1/tax/rates/{year}/brackets` | — | Tax brackets for year |
| GET | `/v1/tax/rates/{year}/deductions` | — | Standard deductions for year |
| GET | `/v1/tax/rates/{year}/special` | — | Special tax rates for year |
| POST | `/v1/tax/calculate` | — | Calculate federal income tax |
| GET | `/v1/tax/questions` | — | Questionnaire questions |
| POST | `/v1/tax/sessions` | — | Start a new session |
| GET | `/v1/tax/sessions/{id}` | — | Get session state |
| PATCH | `/v1/tax/sessions/{id}/answers` | — | Save answers progressively |
| POST | `/v1/tax/sessions/{id}/complete` | — | Compute required forms, mark complete |
| GET | `/v1/tax/sessions/{id}/required-forms` | — | Fetch required forms (completed session) |
| GET | `/v1/tax/periods` | — | List tax periods |
| POST | `/v1/tax/admin/seed-year` | Admin JWT | Seed / inflate a tax year |
| POST | `/v1/tax/admin/update-year` | Admin JWT | Alias for seed-year (contract name) |

## Quick Start

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run tests (SQLite in-memory, no DB needed)
pytest tests/ -v

# Start dev server (requires PostgreSQL)
uvicorn app.main:app --reload --port 8003

# Run with Docker Compose
docker compose up
```

## Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Database connection string |
| `JWT_SECRET` | `change-me-in-production` | HMAC-SHA256 secret (must match main portfolio) |
| `DEFAULT_TAX_YEAR` | `2024` | Year to seed on startup |
| `PORT` | `8003` | Service port |
| `DEBUG` | `false` | Enable SQL echo and verbose logging |
| `CORS_ORIGINS` | `["*"]` | CORS allowed origins (JSON list) |

## Test Suite

```
tests/
├── unit/            # Bracket math, rule engine logic (no HTTP)
├── bdd/             # Gherkin scenarios (pytest-bdd)
├── property/        # Hypothesis DDT (monotonicity, invariants)
├── regression/      # Contract/snapshot tests (API surface stability)
└── e2e/             # Full session flow (httpx.AsyncClient → ASGI)
```

Run specific suites:
```bash
pytest tests/unit/         # fast unit tests
pytest tests/regression/   # contract stability
pytest tests/e2e/          # full session flows
pytest tests/property/     # property-based (may be slow)
pytest tests/bdd/          # BDD scenarios
```

## Architecture

```
app/
├── main.py        factory pattern: create_app(settings=None)
├── config.py      pydantic-settings typed config
├── auth.py        HMAC-SHA256 JWT middleware
├── database.py    async SQLAlchemy (asyncpg/aiosqlite)
├── models.py      SQLAlchemy ORM + Pydantic schemas
├── seed.py        idempotent data seeding (80+ forms, brackets, etc.)
├── engine.py      RuleEngine (O(q) evaluation) + BracketCalculator
├── scheduler.py   APScheduler annual job (Jan 1)
└── routers/
    ├── forms.py   federal + state form endpoints
    ├── rates.py   brackets, deductions, special rates, calculate
    ├── questions.py  questionnaire questions
    ├── sessions.py   session CRUD
    └── admin.py   periods + admin seed trigger
```

## Integration with NexusConsult Portfolio

Add to `server/routes.ts`:
```typescript
const NEXUS_TAX_URL = process.env.NEXUS_TAX_URL || "http://localhost:8003";
app.all("/api/tax/*", proxy(NEXUS_TAX_URL, { proxyReqPathResolver: req => req.path.replace("/api/tax", "/v1") }));
```
