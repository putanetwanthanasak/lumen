# Review gate: 2026-10-15 (Session 7R)

**Scope:** everything merged since the end of day 1. That is PRs #7 to #13, `288d23f..929e07e`: 56 files, +3,816 / −304.

**Method:**
1. An independent review subagent with no prior context. It was read-only (confirmed afterwards with `git status`: no changes) and worked from the full diff, the current `main`, and the user's checklist.
2. I verified every finding that came with a failure scenario against the code, with a reproduction.
3. Automated checks (Part B).

## Findings

| ID | Severity | Title | Where | Status |
|---|---|---|---|---|
| R1 | high (reviewer: medium) | Payment, overdue and cancel events are stored as processed and answered 200 without being applied, so they can never be applied later | `backend/app/webhooks/processor.py` (step 5) | **Fixed in #14** |
| R3 | high | Safety net reads the bank balance without a per-user lock; concurrent purchases can jointly push the bank below 500 | `backend/app/savings/service.py:49-55` | **Deferred to start of Session 8** (decision 2: `SELECT … FOR UPDATE` on `user_balances`) |
| R2 | medium | `months` and `overdue_days` have no upper bound; a value above int4 gives a 500 on every retry instead of a 422 | `backend/app/schemas.py:37,45` | Carry-over |
| R4 | medium | Bank transfer runs before COMMIT; if COMMIT fails, money has moved and a retry debits again | `processor.py` step 5c, `router.py` commit | **Known gap** (decision 1: transactional outbox, not before Oct 19) |
| R5 | low | 422 body echoes caller input in `msg` and unknown keys in `loc` | `backend/app/webhooks/router.py:81-82` | Carry-over |
| R6 | low | Concurrency tests use fixed event and contract ids; a killed run that skips clean-up breaks later runs. `join(timeout)` can return while a request is still in flight. Clean-up does not cover `notifications` yet | `backend/tests/concurrency/` | Carry-over |
| R7 | low | `_credit`'s retry loop relies on READ COMMITTED, but the isolation level is not pinned | `backend/app/db.py:25-26` | Carry-over |
| R8 | low | Test gaps: ID-05 never raced; the contention test never runs the loop (`MAX_CREDIT_ATTEMPTS=0`); ID-03 has at most 40 in flight (anyio threadpool), not 50; no HTTP test of a saving with the app's own bank | tests | Carry-over |
| R9 | low | Migration `223146e7868a`'s `source_vendor` backfill is never run against a row | `backend/alembic/versions/20261015_223146e7868a_…py:54-59` | Carry-over |
| R10 | info | The append-only trigger does not bind the table owner (anyone who owns `audit_log` can disable it) | deployment | Open question (before any real deployment) |

## Details

### R1: high, fixed in #14
- **Reproduced:** a signed `installment_payment_collected` for a contract that doesn't exist returned `200 {"status":"processed"}`.
- **Why high, not the reviewer's medium:** the loss is silent and permanent. Once the event is stored as processed, every resend is a duplicate, so even after Session 8 the payment can't be applied and `paid_amount` stays wrong for good.
- **Fix:** nothing is written and the response is 503, so the platform retries until dispatch exists. The fix PR has a test that failed before the fix, and a break test.

### R3: high, deferred (user decision 2)
- **Scenario:** bank balance 600.00, two concurrent 800.00 purchases. Both read 600 and both pass `600 − 80 ≥ 500`, so the bank ends at 440.
- **Status:** not fixed in this session, by decision. Session 8 starts with the per-user lock and a test that reproduces this.

### R2: medium
- **Reproduced:** `months = 2**40` and `overdue_days = 2**31` both returned 500 (`NumericValueOutOfRange` on insert).
- **Why it matters:** a 500 makes the platform retry, so the same bad event fails forever.
- **Fix:** add `le=` bounds in `Contract`, with WH-04 cases.

### R4: medium, known
Accepted by decision 1. The intended fix is a transactional outbox: record the transfer in the same transaction, perform it after commit, idempotent per savings transaction.

### R5: low
- **Reproduced:** `event_type = "<script>x</script>"` returns 422 with `"msg": "Input tag '<script>x</script>' found …"`.
- **Mitigation:** only an authenticated sender ever sees its own input (the signature is checked first), and the response is JSON.
- **Fix:** return `{type, loc}` only and drop `msg`.

### R6: low
- **Confirmed:** fixed ids `evt_same` and `c_same`, and `thread.join(timeout=120)`.
- **Fix:**
  - Prefix the ids with the per-test user token.
  - Fail hard while any thread is still alive.
  - Add `notifications` to the clean-up in Session 9.

### R7: low
- **Confirmed:** `make_engine` sets no isolation level. Under REPEATABLE READ, a losing writer gets a serialization error (500), not a retry. It is still safe (no double apply), but ID-03 would fail.
- **Fix:** `isolation_level="READ COMMITTED"` in `make_engine`.

### R8, R9: low
Test-coverage gaps; see the table. These are candidates for Session 8's PB-03 and PB-04 work and for a migration data test.

### R10: info
Before any real deployment, run the app as a role that does not own `audit_log`, with INSERT and SELECT only.

### Checked and clean (reviewer and me)
- **Money:**
  - No floats; the Decimal context is explicit.
  - 10% / 10.00 / 500.00, rounded half-up, all or nothing.
  - Cash kinds never save, enforced in three layers (service, engine, reconcile).
  - Strict string money parsing.
  - The saving row, the balance update and the transfer all use one amount.
- **Idempotency:**
  - Primary key `(vendor, event_id)` with ON CONFLICT; `(vendor, contract_id)` with ON CONFLICT.
  - Partial unique indexes.
  - The retry loop is bounded and cannot double-apply.
  - No deadlock cycle.
  - INV-1 is read from one snapshot.
- **Transactions:** everything is in the request session. Reconcile runs before the transfer, and a reconcile failure rolls back and re-raises.
- **Security:**
  - HMAC with `compare_digest` and a ±300 s window.
  - The same 401 body for every failure.
  - A streamed 64 KB cap before auth.
  - Secrets come from env.
  - No SQL built from strings.
  - C0 control characters are blocked.
- **Test fixtures:** the `_test` guard runs before any engine. Disabling the trigger is transactional, lives in `tests/` only, and runs only through the guarded engine.
- **CLAUDE.md:** L41, L46/L52, L47–L51 are all reflected.

## Part B: automated checks

| Check | Result |
|---|---|
| `ruff check`, `ruff format --check`, `mypy app` | clean |
| `pytest --cov=app` | 479 passed, 100% coverage (597 statements); `app/rules`, `webhooks`, `savings`, `ledger` all 100% |
| `pytest -m concurrency`, 20 runs in a row | **20 / 20 passed** |
| Fresh DB: drop + create `lumen_test`, `upgrade head` → `downgrade base` → `upgrade head` | 8 tables → 1 (`alembic_version`) → 8; schema snapshot 3/3 passed; full suite 479 passed on the fresh DB |
| gitleaks 8.30.1 (checksum-verified), full history | 39 commits, no leaks |
| pip-audit (locked requirements, `--strict`) | no known vulnerabilities |
| `.env` tracked? | No. Only `.env.example` is tracked; `.env` is ignored (`.gitignore:2`) |
| Hard rule 5 (`\b(kbank\|kbtg\|kasikorn\w*\|shopee)\b`) | Only CLAUDE.md lines 3 and 33, which are the instructions themselves. None in `backend/` or `.github/`. A plain substring grep also matches `MockBankAccountProvider`, a false positive |
| Rule 10 (em dash in Thai text) | No tracked file contains both Thai text and an em dash. The only em dash in the repo is in CLAUDE.md rule 10's own wording |
| Reconcile over every user in the dev DB `lumen` | 1 user checked, **0 violations** (before the smoke test) |
| E2E smoke on the dev DB (real app, env secret, real clock, the app's mock bank) | new user `smoke_1792071109` opted in. Purchase of 800.00 → **200 processed**, auto_save **80.00**, balance 80.00 (v1), mock bank **9,920.00**. Same event again → **200 duplicate**, bank unchanged. Cash withdrawal of 15,000.00 → **200 processed**, no saving. Reconcile clean |
| Decision 3: the reconcile error log names vendor, event_id and invariant | Yes. The message is `reconcile failed, event rolled back: invariants violated for user <u>: INV-1 (vendor=<v> event_id=<e>)`, asserted in `test_RS_02_violation_rolls_back_whole_event_and_logs` |
