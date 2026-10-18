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
docker compose up -d          # Postgres 16 on 127.0.0.1: databases lumen + lumen_test, role lumen_app

cd backend
uv sync                       # create .venv from uv.lock (uvicorn is pinned there)
uv run alembic upgrade head   # runs as MIGRATION_DATABASE_URL (the superuser); never create_all
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000   # http://127.0.0.1:8000/health
```

The server binds to `127.0.0.1` only. There is no end-user auth in this prototype
(`X-Demo-User` names the user, L60), so never use `--host 0.0.0.0` and do not use
`--reload` for a demo. `/docs` is off unless `DEBUG=true`.

### Database roles (S2)

The app connects as `lumen_app`: not a superuser, owns no table, and has no
`DELETE` or `TRUNCATE` anywhere (`audit_log` and `savings_transactions` are
insert-only). Only Alembic and the test clean-up use the `POSTGRES_USER` superuser.

| `.env` key | Role | Used by |
|---|---|---|
| `DATABASE_URL`, `TEST_DATABASE_URL` | `lumen_app` | the app, the tests |
| `MIGRATION_DATABASE_URL`, `TEST_MIGRATION_DATABASE_URL` | `POSTGRES_USER` | `alembic upgrade`, test migrations and clean-up |
| `LUMEN_APP_PASSWORD` | | creates `lumen_app` on first container init |

The role is created by `docker/postgres/init/02-create-app-role.sh`, and Docker runs
init scripts only on an **empty** volume. If your volume predates the role, reset it
(this deletes the local database, which holds only demo data):

```bash
# 1. In .env: set LUMEN_APP_PASSWORD, point DATABASE_URL and TEST_DATABASE_URL at
#    lumen_app, and copy the old superuser URLs to MIGRATION_DATABASE_URL and
#    TEST_MIGRATION_DATABASE_URL (see .env.example).
docker compose down -v        # stop Postgres and delete the pgdata volume
docker compose up -d --wait   # fresh init: lumen, lumen_test, lumen_app
cd backend
uv run alembic upgrade head   # schema + the lumen_app grants
uv run pytest -q              # the S2 tests check you are really connected as lumen_app
```

To keep existing data instead, run the same script in the running container (it
skips the role if it exists), then upgrade:

```bash
set -a; . ./.env; set +a
docker compose exec -T -e LUMEN_APP_PASSWORD postgres sh -s < docker/postgres/init/02-create-app-role.sh
cd backend && uv run alembic upgrade head
```

## Quality checks

From `backend/`:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest --cov=app        # add -m "not db" to skip tests needing Postgres
```

CI (GitHub Actions) runs the same checks plus `pip-audit` and a full-history `gitleaks` scan.
