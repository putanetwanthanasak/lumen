# Lumen

> **Concept prototype for a hackathon. Not an official product.**

Lumen receives BNPL debt webhooks from (simulated) external platforms, builds an
installment ledger, auto-saves a small amount on each purchase, and alerts the user
on every new debt.

## Run locally

Requirements: Docker with Compose, [uv](https://docs.astral.sh/uv/) (Python 3.14 is
installed by uv if needed).

```bash
git config core.hooksPath scripts/hooks   # enables the pre-push guard (no pushes to main)
cp .env.example .env          # fill in values; .env is git-ignored
docker compose up -d          # Postgres 16 on 127.0.0.1, databases lumen + lumen_test

cd backend
uv sync                       # create .venv from uv.lock
uv run alembic upgrade head      # create/upgrade the schema (never create_all)
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000/health
```

## Quality checks

From `backend/`:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest --cov=app        # add -m "not db" to skip tests needing Postgres
```

CI (GitHub Actions) runs the same checks plus `pip-audit` and a full-history `gitleaks` scan.
