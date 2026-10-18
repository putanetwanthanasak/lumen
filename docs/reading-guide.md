# Reading guide: the whole backend (for 2026-10-19)

About two hours. It follows one request through the system: **webhook → ledger → savings
→ alerts → dispute**, then the data layer and the tests that pin it down. Line numbers
refer to the code after PRs #21, #22 and the demo PR (`chore/demo-script-and-reading-guide`).
If one of them is not merged yet, read that branch.

Older guide (day 1, foundation only): `docs/reading-guide/2026-10-13.md`.

## The flow on one page

```
POST /webhooks/bnpl
  main.py            TrustedHost (S8) ─ DB-error handler (S12)
  webhooks/router    64 KB cap → HMAC + 300 s window → strict schema (422)
  webhooks/processor
    step 4   INSERT webhook_event ON CONFLICT DO NOTHING   (vendor, event_id)  L47
             └ already there? same hash → duplicate / 202 / 409 again; else 409 + audit
    step 5   lock_contract (advisory lock per vendor:contract)
             created → 5a installment (UNIQUE vendor+contract)
                       5b auto_save (lock balance, compute_saving, ledger row, credit)
                       5f replay pending_parent events
                       5e new-debt alert row (L43 total from debts.summary)
             payment / overdue / cancel → apply_event, or pending_parent if no installment
    step 6   audit row
    step 7   reconcile: INV-1/2/3/5, L51 → any violation rolls everything back
    step 5c  bank.transfer_to_savings(idempotency_key=…)   (S1, before COMMIT)
  router     COMMIT → step 9 push (after commit, never fails the webhook)

POST /debts/{id}/not-me
  disputes/router    owner check → dispute() → COMMIT → send_signal() → COMMIT
GET /debts/summary   debts/service.summary (the same function the alert uses)
```

## Reading order

Times are a guide. "Must read" = money, SQL, transactions, migrations, security.

### 1. Entry and edges (10 min)

**`backend/app/main.py`**: must read
- `ALLOWED_HOSTS` (18) and `create_app` (30-50): every request passes the Host check first (DNS rebinding, S8); `/docs` exists only with `DEBUG` (S12).
- `_db_error` (21-27): a DB exception becomes a bare 500 and is logged only as SQLSTATE and constraint, because Postgres's error text quotes the failing row.

**`backend/app/webhooks/router.py`**: must read
- `_read_body` (48-55): the 64 KB cap is checked while streaming, before any signature or JSON work (L55).
- `verified_request` (58-76): one 401 body for every authentication failure, so a caller can't tell which check failed.
- `receive_webhook` (80-100): parse → `process_event` → **commit** → `deliver`. The order matters: the push never runs for an uncommitted event. 422 bodies drop `msg` (R5).

**`backend/app/webhooks/signature.py`**: must read
- `verify` (40-65): the format checks run before the HMAC. The window is `abs(now - ts) > 300`. `hmac.compare_digest` over `timestamp + "." + raw body`, so the verified bytes are exactly the parsed bytes.

### 2. What a valid event is (10 min)

**`backend/app/money.py`**: must read
- `MONEY_PATTERN` (20), `MONEY_MAX` (22), `_parser` (34-44): money must arrive as a JSON string, with at most 2 places and below 1E10. It is rejected, never rounded (L49). `MONEY_MAX` exists because a *sum* can still overflow (S7).

**`backend/app/schemas.py`**: must read
- `Contract` (37-50), `_ContractCreated._kind_matches_event_type` (69-72), `NO_CONTROL_CHARS` (21), and the bounds at 27-28 (L55, L59 6): every rule that turns bad input into a 422 instead of a 500.

### 3. The processor: the heart (25 min)

**`backend/app/webhooks/processor.py`**: must read, slowly
- Step 4 (85-128): `INSERT … ON CONFLICT DO NOTHING RETURNING` on `(vendor, event_id)`. Exactly one of N copies gets a row back. A repeat compares canonical hashes (`payload_hash`, 58-62) to choose duplicate (200), pending (202), the first 409 again (`_rejected_again`, 252-263, L59 1), or a reused id (409 + audit).
- Step 5 (130-154): `lock_contract` comes first. Then the created branch: installment → auto-save → replay pending → alert, in that order (the comment at 142 explains why the alert comes last).
- Steps 6 and 7 (156-183): audit, then `reconcile.assert_user_invariants`. A violation rolls back the whole event and is logged without the user ref.
- Step 5c (185-191): the bank transfer comes **last**, after reconcile, with a key from `(vendor, event_id)` (S1).
- `_apply` (204-230) and `_claimed` (233-237): rejections are stored and audited under the installment *owner* (S10).
- `_contract_reused` (266-311): ID-05, a new event_id for an existing contract.

### 4. The ledger (15 min)

**`backend/app/ledger/service.py`**: must read
- `create_installment` (55-84): the UNIQUE `(vendor, contract_id)` decides ID-05, so a racing second create gets `None`.
- `lock_contract` (107-116): `pg_advisory_xact_lock(hashtextextended(vendor:contract))`. The docstring is the reason for the lock: a payment racing its created event.
- `apply_event` (132-161): the user check, INV-6 (`paid ≤ owed`), the S7 cap, and late fees *set* not added (L55). `_settle` (164-171) never touches `cancelled` or `disputed`.
- `_is_stale` (174-191): an older overdue never lowers the late fee.

### 5. Savings (15 min)

**`backend/app/rules/engine.py`**: must read
- `compute_saving` (39-84): 10%, rounded half-up to satang, clamped to 10..500, and **0** if the bank balance would drop below the safety net (L46, L52). Pure, no I/O.

**`backend/app/savings/service.py`**: must read
- `transfer_key` (28-33): why the key isn't `savings_tx_id`.
- `auto_save` (36-86): cash kinds return before anything else (INV-5); no consent means no saving. `_lock_balance` (89-98) serializes one user's savings so two can't jointly pass the safety net. `_credit` (101-125) is optimistic locking on `version`.

**`backend/app/ledger/reconcile.py`**: must read
- `check_user_invariants` (35-135): INV-1 and INV-2 come from one snapshot (40-63); INV-3 (65-75), INV-5 (77-98), L51 (100-119). This is the second line of defense behind the DB constraints.

### 6. Alerts (10 min)

**`backend/app/notifications/service.py`**: must read
- `notify_new_debt` (27-60): the L43 total comes from `debts.summary`, so the alert and the summary can never disagree. The partial UNIQUE means one alert per installment.
- `deliver` (63-92): after commit, never raises, and records `pushed` / `inbox_only`. Errors are logged without user data (S12).

**`backend/app/debts/service.py`**: must read
- `still_owed` (44-45) and `summary` (86-119): what "owed" means (a disputed debt still counts until cancelled).

### 7. "Not me" (15 min)

**`backend/app/disputes/service.py`**: must read
- `dispute` (57-130): owner lookup → `lock_contract` → `UPDATE … WHERE disputed_at IS NULL RETURNING`. Only the first report audits and marks the alert. `disputed_at` is never cleared (L59 3).
- `send_signal` (133-169): the lock is held across the platform call; `sent` short-circuits; otherwise it stores `sent` or `failed` (S4, L60 2).

**`backend/app/disputes/router.py`**: must read
- `not_me` (102-126): two commits, the report first, then the signal. A malformed id, an unknown id and another user's id all get the same 404.
- `MESSAGE_SENT` / `MESSAGE_NOT_SENT` (39-48) and `_response` (76-92): the message is chosen from the stored status (L60 3) and never claims Lumen can cancel the transaction (L42).

### 8. Data layer and roles (15 min)

**`backend/app/models.py`**: must read
- `Installment` (142-201): the CHECKs, including INV-6 and the two dispute CHECKs.
- `SavingsTransaction` (204-257): the two partial UNIQUEs (225-242), one auto-save per event and per installment.
- `Notification` (298-333): one new-debt alert per installment (312-316).
- `AuditLog` (336-359): append-only (a trigger), one dispute row per installment (344-348).

**Migrations** in `backend/alembic/versions/`:
- must read: `…_a1c3e5f7b9d2_app_role_grants.py`, the whole grant set for `lumen_app` (S2);
- must read: `…_c4e6a8b0d2f4_dispute_signal_status.py`;
- skim the rest; `tests/db/test_schema_snapshot.py` holds what they produce.

**`backend/app/db.py`**: must read
- `make_engine` (27-38): READ COMMITTED (R7) and `hide_parameters`.
- `describe_db_error` (41-51).

**`docker/postgres/init/02-create-app-role.sh`**: must read. The role attributes; the password comes from env.

### 9. Tests that define the behavior (15 min)

- `tests/concurrency/test_idempotency_concurrency.py`: ID-02, the same event 8 times at once.
- `tests/concurrency/test_dispute_concurrency.py`: the lock probes; read the docstring first.
- `tests/db/test_app_role.py`: the `ATTACKS` table.
- `tests/rules/test_properties.py` and `tests/processing/test_event_properties.py`: the Hypothesis properties (PB-01..04).
- `tests/demo/test_demo_smoke.py`: the six demo scenes as assertions.

## Safe to skim

- `app/config.py`, `app/users.py`, `app/audit/service.py`, `app/notifications/copy.py` (wording), `app/rules/config.py`, `app/providers/*` (mocks and the Protocol).
- `alembic/env.py`, the older migrations, `backend/pyproject.toml`, `uv.lock`.
- `tests/db/factories.py`, `tests/webhooks/payloads.py`, the `conftest.py` files (except `tests/conftest.py`'s two engines).
- `backend/demo/script.py`: the presenter's script, not product code.
- `.github/workflows/ci.yml`: only the "Create the app DB role" step is interesting.

## Self-check questions

Answer each in a sentence or two, then open the file to check.

1. What stops the same event from saving twice, even when eight copies arrive at once? *(`app/webhooks/processor.py`, step 4; `app/models.py`, `SavingsTransaction`)*
2. Why is there a per-contract lock, and what would go wrong without it? *(`app/ledger/service.py`, `lock_contract`; `tests/concurrency/test_dispute_concurrency.py`)*
3. A platform sends money as the JSON number `1200.5`. What does it get back, and why not a rounded value? *(`app/money.py`; `app/schemas.py`)*
4. The commit fails after the bank transfer, and the platform retries. Why is the user debited only once, and what can still go wrong? *(`app/savings/service.py`, `transfer_key`; `docs/security.md`)*
5. Where does the monthly total in an alert come from, and why can it never disagree with `GET /debts/summary`? *(`app/notifications/service.py`, `notify_new_debt`; `app/debts/service.py`)*
6. A user taps "Not me" while ShopDemo is down, then again after it recovers. What does each tap's message say, and how many reports does ShopDemo get? *(`app/disputes/service.py`, `send_signal`; `app/disputes/router.py`)*
7. If someone stole `DATABASE_URL`, could they erase the dispute history? What stops them? *(`alembic/versions/…_a1c3e5f7b9d2_app_role_grants.py`; `tests/db/test_app_role.py`)*
8. When is a saving skipped even though the user opted in? *(`app/rules/engine.py`, `compute_saving`; `app/savings/service.py`, `auto_save`)*
9. A payment arrives before its installment exists. What is stored, what is answered, and when is it applied? *(`app/webhooks/processor.py`, `_replay_pending`; `app/ledger/service.py`, `pending_payloads`)*
10. Which bugs would the DB catch even if the Python had one, and which only `reconcile` catches? *(`app/models.py`; `app/ledger/reconcile.py`)*
