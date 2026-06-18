# Contributing to nexus-tax

Thank you for your interest in contributing!

## Getting started

1. Fork the repository and clone your fork.
2. Install dev dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```
3. Copy `.env.example` to `.env` and fill in your values.
4. Run the test suite to confirm everything is green:
   ```bash
   pytest
   ```

## Branch strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, always deployable |
| `feature/<name>` | New features |
| `fix/<name>` | Bug fixes |
| `chore/<name>` | Tooling, deps, refactors |

All PRs target `main`.  Do **not** push directly to `main`.

## Commit format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]
[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```
feat(engine): add anyio.to_thread offload for large rule sets
fix(scheduler): switch stdlib logging → structlog to prevent TypeError
test(bdd): add sync bridge for pytest-bdd step functions
```

## Code standards

- Python 3.11+, formatted with **black** + **isort**
- Type annotations on all public functions
- No bare `except` clauses — always catch specific exceptions
- Use `structlog` for all log calls (not `logging.info(msg, key=val)`)
- All new endpoints need at minimum a regression/contract test

## Running specific test suites

```bash
pytest tests/unit/           # fast, no HTTP
pytest tests/regression/     # HTTP contract (in-memory DB)
pytest tests/e2e/            # full session flows
pytest tests/bdd/            # Gherkin scenarios
pytest tests/property/       # Hypothesis property tests
pytest --cov=app             # coverage report
```

## Pull request checklist

- [ ] Tests added / updated for the change
- [ ] `pytest` passes locally (all suites)
- [ ] Docstring added for new public functions
- [ ] GUIDE.md updated if new endpoints or config vars are added
- [ ] `CHANGELOG` entry (if applicable)

## Code of conduct

Be respectful and constructive.  We follow the
[Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
