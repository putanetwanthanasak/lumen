# KidNee (คิดหนี้)

[![CI](https://github.com/putanetwanthanasak/lumen/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/putanetwanthanasak/lumen/actions/workflows/ci.yml)

**KidNee: see your total BNPL installments before you buy, and keep a savings buffer for the months that go over budget.**

A concept prototype: a FastAPI and PostgreSQL ledger of buy-now-pay-later installments
with a React mobile UI. "Lumen" is the code name you will see in the repository.

## Demo

| Home | Check before you buy | Months and the buffer | Using the buffer |
|:---:|:---:|:---:|:---:|
| <img src="docs/images/home.png" width="200" alt="Home screen: this month's installment total against the budget, the buffer balance and the AI summary"> | <img src="docs/images/check-result.png" width="200" alt="Check result: a red verdict and a bar for every month's total if this installment is taken"> | <img src="docs/images/months-buffer.png" width="200" alt="Monthly totals: months over budget show what the buffer already covers and what is still short"> | <img src="docs/images/buffer-move.png" width="200" alt="Buffer screen: moving the over-budget amount back to the main account, step by step"> |
| This month's total against your budget, the buffer, and a short AI summary | A new 12-month installment: two months above a third of income (red), six over budget (amber) | Each month's total; teal is what the buffer already set aside | Move the buffer back to the main account before the BNPL app collects |

Screens are 390x844 and in Thai; every figure is mock data from the seeded demo personas.
A 61-second demo video is available on request.

## The problem
- BNPL installments live in several apps, and none of them shows what you owe **per month across all of them**.
- Each plan looks small at checkout. The trouble is the overlap: months later, several plans fall due together and the month goes over budget.
- When that month comes, nothing has been set aside for it.

KidNee answers with two features:
- **Check before you buy** (เช็กก่อนผ่อน): type the price and the months, or the monthly amount. KidNee shows every future month's total with the new installment against your budget and one third of your income: green (within budget), amber (over budget) or red (over a third of income, the central bank's financial-literacy guidance). It is advice only; recording always works.
- **The buffer** (กันชน): each recorded installment moves a saving you choose (a percentage of the price or a fixed amount) from the main account into a buffer, skipped whole if the main account would fall below 500 THB. Months over budget show what the buffer covers, and you move that money back yourself; nothing moves automatically.

The code also has new-debt alerts and a "Not me" report for debts that arrive by webhook; they are tested but not in the screens demo.

## Architecture

```mermaid
flowchart LR
    vendor["Simulated BNPL vendor<br/>(ShopDemo)"] -->|"signed webhook<br/>HMAC-SHA256"| hook
    ui["React UI<br/>(KidNee screens)"] -->|"/api: manual entry,<br/>check before you buy,<br/>buffer moves"| svc

    subgraph api["FastAPI on 127.0.0.1"]
        hook["Webhook receiver<br/>413, 401, 422, 409"]
        svc["Ledger, auto-save,<br/>affordability, buffer"]
        plan["Plan: every number<br/>computed in Decimal"]
        ai["AI summary:<br/>grounding check + fallback"]
    end

    hook --> svc
    svc --> db[("PostgreSQL 16<br/>Numeric(12,2) ledger,<br/>append-only audit log")]
    svc --> bank["Mock bank provider<br/>(main account and buffer)"]
    db --> plan --> ai
    ai -.->|"numbers and months only"| llm["Claude model<br/>(optional)"]
    ai -->|"text whose every number<br/>is one of the plan's"| ui
```

In the demo, one loopback server mounts the API at `/api` and the built UI at `/`
([`backend/app/serve.py`](backend/app/serve.py)).

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.14, FastAPI, Pydantic 2, SQLAlchemy 2.1, Alembic |
| Database | PostgreSQL 16 in Docker Compose, bound to 127.0.0.1 |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4 |
| AI (optional) | Claude through the Anthropic SDK, behind a grounding check |
| Tests | pytest, Hypothesis, pytest-cov (line and branch), node:test |
| Gates in CI | ruff, mypy `--strict`, coverage floors, pip-audit, npm audit, gitleaks |
| Tooling | uv and npm with lock files, GitHub Actions |

## Engineering decisions worth reading
- **Money is `Decimal` and `Numeric(12,2)` end to end.** The API takes money only as a JSON string with at most 2 decimals; a JSON number or a third decimal is a 422, never rounded ([`backend/app/money.py`](backend/app/money.py), [`tests/db/test_money_types.py`](backend/tests/db/test_money_types.py)). The browser only formats and compares those strings, and a test fails if a screen adds amounts up ([`frontend/src/money.ts`](frontend/src/money.ts), UI-51 in [`frontend/tests/wiring.test.ts`](frontend/tests/wiring.test.ts)).
- **Webhooks: HMAC plus an idempotency key of `(vendor, event_id)`.** HMAC-SHA256 over `timestamp.body`, a constant-time compare and a 5-minute window ([`signature.py`](backend/app/webhooks/signature.py)). A body over 64 KB is a 413 before the signature is checked, a bad signature a 401, a bad payload a 422 ([`router.py`](backend/app/webhooks/router.py)). The same key with a different payload is a 409 with an audit row; the same payload again is a duplicate with no second saving or alert ([`processor.py`](backend/app/webhooks/processor.py)).
- **Per-user row locking for concurrent money moves.** Every saving locks the user's balance row (`SELECT ... FOR UPDATE`) before it reads the bank balance, and every buffer move locks it before it reads the buffer, so two concurrent purchases cannot both pass the 500 THB safety net and two moves cannot overdraw the buffer ([`savings/service.py`](backend/app/savings/service.py), [`buffer/service.py`](backend/app/buffer/service.py)). The isolation level is pinned to READ COMMITTED ([`db.py`](backend/app/db.py)).
- **A separate database role, so the app cannot alter the audit log.** The app connects as `lumen_app`: not a superuser, owns no table, no `DELETE` or `TRUNCATE` anywhere, and `audit_log` and `savings_transactions` are insert-only. Only migrations and the test clean-up use the superuser ([grants migration](backend/alembic/versions/20261018_a1c3e5f7b9d2_app_role_grants.py)). A test runs 18 tampering statements as the app role and expects each to be refused ([`tests/db/test_app_role.py`](backend/tests/db/test_app_role.py)).
- **The AI never computes a number.** Code computes the plan; the model only words it, and gets numbers and months only, never user text. Every reply must pass a grounding check (every number and month must be one of the inputs, and known wrong claims are refused) or the card shows a template built from the same numbers ([`assistant/summary.py`](backend/app/assistant/summary.py), [`ai/grounding.py`](backend/app/ai/grounding.py)).

## Quality

From the latest CI run on `main` ([run 42561485817](https://github.com/putanetwanthanasak/lumen/actions/runs/42561485817), 2026-11-09, commit `f95fcd6`):

| Check | Result |
|---|---|
| Backend tests (pytest, real PostgreSQL) | 1,806 passed |
| Backend coverage of `backend/app` | 100.00% of lines and branches (3,105 statements, 502 branches); CI fails below 80% overall or 90% in each money module |
| Frontend tests (node:test) | 300 passed, plus `tsc`, the build and `npm audit` |
| Static checks | ruff, ruff format, mypy `--strict` clean |
| Supply chain and secrets | pip-audit and npm audit clean; gitleaks over the full history, no findings |

- **Property-based tests:** 22 Hypothesis properties in 10 test files, for the money parser, the saving rule, event processing, the monthly totals and the AI grounding check (for example [`tests/rules/test_properties.py`](backend/tests/rules/test_properties.py), [`tests/processing/test_event_properties.py`](backend/tests/processing/test_event_properties.py)).
- **Concurrency tests:** 28 tests with real threads and committed transactions against PostgreSQL ([`backend/tests/concurrency/`](backend/tests/concurrency/)), run in CI with the rest.
- **Break before trust:** for critical tests (money, idempotency, invariants, security, and the key UI rules), I broke the code on purpose, confirmed the test failed for the right reason, and restored it. Over 500 break tests, backend and frontend, are recorded in [`docs/progress/`](docs/progress/).
- **Independent review:** since 2026-10-26, every PR is reviewed by a read-only reviewer subagent that sees the branch and the project rules, not the author's summary ([`.claude/agents/independent-reviewer.md`](.claude/agents/independent-reviewer.md)); each finding and how it was handled is in the PR and the progress log. Earlier work went through a review gate and an OWASP API Top 10 security review ([`docs/reviews/`](docs/reviews/)).

**The race test that could not fail.** With the row lock removed, the safety-net race test still passed 20 runs out of 20. The test's user had no balance row yet, so PostgreSQL's `INSERT ... ON CONFLICT DO NOTHING` made the second transaction wait for the first to commit: the test serialised itself. A second case for a user who has saved before now fails 13 times out of 20 without the lock (two savings, and the bank balance drops from 600 to 440, under the 500 safety net). A deterministic probe also checks that the row is locked before the bank balance is read ([`test_safety_net_concurrency.py`](backend/tests/concurrency/test_safety_net_concurrency.py), [log](docs/progress/2026-10-16.md)).

**The transfer that succeeded when the commit failed.** An auto-save transfer runs just before `COMMIT`. If the commit was lost, the retry decided the saving again from a balance that already showed the first transfer. Near the 500 THB safety net it saved 0.00 while 300.00 had already left the main account, with no ledger row. After a rule change the bank refused a different amount under the same idempotency key, so every retry failed and the installment was never recorded. Now `auto_save` first asks the bank what it already moved under that key and records exactly that. The tests that reproduced it fail without the fix ([`test_manual_entry.py`](backend/tests/installments/test_manual_entry.py), [`test_bank_idempotency.py`](backend/tests/webhooks/test_bank_idempotency.py), PR #53).

## Run it locally

You need Docker with Compose, [uv](https://docs.astral.sh/uv/) (it installs Python 3.14), and Node.js 22.18 or later with npm.

```bash
git clone https://github.com/putanetwanthanasak/lumen.git
cd lumen

# Local-only settings. .env is git-ignored; change the passwords if you like.
cat > .env <<'EOF'
POSTGRES_USER=lumen
POSTGRES_PASSWORD=local-dev-only
POSTGRES_PORT=5432
LUMEN_APP_PASSWORD=local-app-only
DATABASE_URL=postgresql+psycopg://lumen_app:local-app-only@127.0.0.1:5432/lumen
TEST_DATABASE_URL=postgresql+psycopg://lumen_app:local-app-only@127.0.0.1:5432/lumen_test
MIGRATION_DATABASE_URL=postgresql+psycopg://lumen:local-dev-only@127.0.0.1:5432/lumen
TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://lumen:local-dev-only@127.0.0.1:5432/lumen_test
WEBHOOK_SECRET_SHOPDEMO=local-demo-webhook-secret
EOF

docker compose up -d --wait                       # PostgreSQL 16 on 127.0.0.1:5432
(cd frontend && npm ci && npm run build)          # writes frontend/dist
cd backend
uv sync --frozen                                  # Python deps from uv.lock
uv run python -m demo.kidnee reset --yes          # drop, migrate and seed the demo database
uv run python -m demo.kidnee serve                # open http://127.0.0.1:8000
```

If port 5432 is already in use, change `POSTGRES_PORT` and the port in the four URLs.
The demo uses its own database, `lumen_kidnee`. Use the **Demo** button to switch
between the three personas: `demo-mon` (within budget), `demo-over` (over budget, and
the buffer covers it) and `demo-consolidate` (a long run over budget). Run `reset --yes`
again at any time for a clean demo, then restart `serve`. Without an API key, the AI
card shows its template; to try the model, add `LLM_PROVIDER=anthropic` and your own
`LLM_API_KEY` to `.env`.

The webhook path has its own terminal demo in six scenes (press Enter between them): a
clean database, a signed ShopDemo purchase, the same webhook again (a duplicate, no second
saving), a cash withdrawal with its strong alert, "Not me" on it, and the debt summary.
It uses its own database, `lumen_demo`. From `backend/`:

```bash
uv run python -m demo
```

**Tests and checks.** From `backend/`, with PostgreSQL up (the tests migrate `lumen_test` themselves):

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app
uv run pytest --cov=app                           # all tests, including concurrency
uv run pytest -m concurrency -v                   # only the race tests
cd ../frontend && npm test                        # frontend tests
```

## Project structure

```
backend/
  app/             FastAPI app: webhooks, ledger, savings, buffer, affordability, assistant, ai
  alembic/         migrations: schema, triggers, the app role's grants
  demo/            the terminal webhook demo and the one-server screens demo
  tests/           unit, property, database and concurrency tests
frontend/
  src/             React screens, Thai copy, display-only money formatting
  tests/           node:test suites (UI-01 to UI-72)
docker/postgres/   first-run scripts: the test database and the app role
docs/
  api/             the screens' API, with exact JSON
  progress/        daily logs: plans, break tests, bugs, review findings
  reviews/         the review gate and the security review
.claude/           Claude Code skills, the reviewer subagent and its hooks
CLAUDE.md          project rules for the AI pair programmer
DESIGN.md          the UI design system and screen specs
```

The product and architecture specs (in Thai) are not published; `CLAUDE.md`,
`DESIGN.md` and the logs refer to them as `docs/spec/`.

## Limitations
- A concept prototype, not a product.
- The bank account is simulated by a mock provider; no real money moves.
- The webhook is tested with a simulated vendor (ShopDemo) whose contract is an assumption, not a real platform's API.
- There is no real authentication: a demo header (`X-Demo-User`) names the user.
- It runs on localhost only: the server and the database bind to 127.0.0.1.
- Usability has not yet been tested with users.
- The auto-save transfer still runs before the database commit. If the commit is lost, the retry records what the bank moved, but a request that is never retried leaves that transfer unrecorded. The planned fix, a transactional outbox, is not built.

## Context
Built solo in about 5 weeks (October to November 2026) for the KBTG Kampus Hackathon
2026, Track 1 Software Engineering & Quality; selected among 30 teams to pitch.
Developed with Claude Code as an AI pair programmer; every change went through tests,
review and my own merge.

## Disclaimer
A concept prototype built for a competition. It is not affiliated with or endorsed by
any bank, and it is not a real financial product.
