# CI / CD

nexus-tax uses **GitHub Actions** for continuous integration and delivery.

## Pipelines

### CI — `.github/workflows/ci.yml`

Triggered on every push and pull request to `main`.

| Stage | What it runs |
|-------|-------------|
| **lint** | `black --check`, `isort --check`, `mypy` |
| **unit** | `pytest tests/unit/ tests/regression/ tests/bdd/ tests/property/` |
| **e2e** | `pytest tests/e2e/` |
| **docker** | `docker build` (smoke-test the image builds) |

All stages run in parallel where there are no dependencies.  The `docker`
stage runs after `unit` passes.

### CD — deploy on tag

When a tag matching `v*.*.*` is pushed:
1. CI must pass on the tagged commit.
2. Docker image is built and pushed to GHCR (`ghcr.io/itkdaniel/nexus-tax`).
3. The image is deployed (via K8s rolling-update or Compose pull) to the
   configured environment.

## Environment secrets (GitHub Actions)

| Secret | Description |
|--------|-------------|
| `DATABASE_URL` | PostgreSQL async URL for CI test DB |
| `JWT_SECRET` | HMAC secret (random 64-char hex) |
| `GHCR_TOKEN` | GitHub PAT with `packages:write` for image push |

Set these under **Settings → Secrets and variables → Actions** in the
repository.

## Local simulation

Run exactly what CI runs:

```bash
# Lint
black --check app tests
isort --check-only app tests

# Tests (all suites)
pytest

# Docker build
docker build -t nexus-tax:local .
```

## Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** — breaking API change
- **MINOR** — new endpoint or backwards-compatible feature
- **PATCH** — bug fix

The `version` field in `app/config.py` is the source of truth and must match
the git tag.
