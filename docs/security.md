# Lumen security

A concept prototype, run by one presenter on one laptop. This page covers what it
defends against today, which test proves each control, and what is still missing
for a real deployment. Source: the independent review `docs/reviews/2026-10-18-security.md`
(S1 to S12) and the decisions in CLAUDE.md (L60, L61).

## Threat model

- **Assets:** the installment ledger, the savings ledger and balance, the alerts, and
  the dispute history ("Not me" reports and the audit log).
- **Who can reach it:** BNPL platforms send signed webhooks; the end user calls the API.
  In the prototype both run on `127.0.0.1`.
- **What we defend against:** forged or replayed webhooks; duplicate deliveries that
  would save or alert twice; one user reading or disputing another's debt; history
  erased or rewritten through the app's DB connection; personal data in logs; a
  web page in the presenter's browser calling the local API (DNS rebinding).
- **Out of scope for now:** a hostile end user with network access (there is no
  end-user auth, see the gaps below), and the host itself.

## Controls in place

| Control | Where | Proving test |
|---|---|---|
| HMAC-SHA256 over `timestamp.body`, constant-time compare, lowercase hex only | `webhooks/signature.py` | `tests/webhooks/test_signature.py::test_signature_covers_timestamp_dot_raw_body`, `test_router.py::test_WH_02_*` |
| Replay window of 300 s in both directions | `webhooks/signature.py` | `test_router.py::test_WH_03_*` |
| Body over 64 KB gets 413 before signature check or parsing | `webhooks/router.py` | `test_router.py::test_body_over_size_limit_rejected_before_signature` |
| Strict schema: money as strings, no extra fields, no control characters; 422 never quotes the input | `schemas.py`, `money.py` | `test_schemas.py`, `test_router.py::test_WH_04_R5_422_does_not_quote_the_input_back` |
| Idempotency by `(vendor, event_id)` (L47); a different payload gets 409 and an audit row | `webhooks/processor.py` | `test_router.py::test_ID_01_*`, `tests/concurrency/test_idempotency_concurrency.py::test_ID_02_*` |
| One saving and one alert per contract, enforced by the DB | migrations, partial UNIQUE indexes | `tests/db/test_auto_save_per_installment.py`, `test_schema_snapshot.py` |
| Per-contract lock: payment, overdue, cancel and "Not me" never overwrite each other | `ledger/service.py::lock_contract` | `tests/concurrency/test_dispute_concurrency.py::test_L42_dispute_waits_for_the_contract_lock` |
| Bank transfer idempotency key per `(vendor, event_id)` (S1, partial) | `savings/service.py::transfer_key`, `providers/mock_bank.py` | `tests/webhooks/test_bank_idempotency.py::test_S1_commit_fails_after_transfer_retry_debits_the_bank_once` |
| Amounts that would overflow `Numeric(12,2)` get 409, not a 500 on every retry (S7) | `ledger/service.py::apply_event` | `test_router.py::test_S7_payment_that_would_overflow_paid_amount_answered_409` |
| Only the owner sees or disputes a debt; others get the same 404 as an unknown id | `debts/`, `disputes/` | `test_not_me.py::test_L42_only_the_owner_can_dispute_others_get_the_same_404`, `test_summary.py::test_summary_shows_only_the_callers_debts` |
| "Not me" stores the platform signal status and never claims it was sent when it was not; a repeat tap re-sends until `sent` (S4, L60) | `disputes/service.py::send_signal` | `test_not_me.py::test_L60_2_*`, `test_S4_*`, `tests/concurrency/test_dispute_concurrency.py::test_S4_*` |
| Dispute history kept: `disputed_at` never cleared; one dispute audit row per installment | CHECKs and a partial UNIQUE index | `test_not_me.py::test_L59_3_cancel_after_dispute_keeps_the_dispute_history`, `tests/db/test_constraints.py` |
| Audit rows filed under the owner, never the claimed user (S10) | `webhooks/processor.py::_claimed` | `tests/processing/test_contract_events.py::test_S10_*` |
| App DB role `lumen_app`: not a superuser, owns nothing, no DELETE or TRUNCATE; audit and savings are insert-only (S2) | `docker/postgres/init/02-create-app-role.sh`, migration `a1c3e5f7b9d2` | `tests/db/test_app_role.py`, `test_schema_snapshot.py::test_S2_app_role_grants_match` |
| Audit log append-only even for the owner (trigger) | initial migration | `tests/db/test_audit_log.py` |
| No user refs or alert text in logs: hidden SQL parameters, DB errors logged as SQLSTATE and constraint only (S12) | `db.py::describe_db_error`, `main.py::_db_error` | `tests/webhooks/test_log_privacy.py` |
| `/docs`, `/redoc`, `/openapi.json` only with `DEBUG=true` (S12) | `main.py::create_app` | `tests/test_app_docs.py` |
| Only loopback `Host` headers served, which blocks DNS rebinding (S8) | `main.py::ALLOWED_HOSTS` | `tests/test_trusted_host.py` |
| uvicorn pinned in `uv.lock`, run on `127.0.0.1`, no `--reload` (S9, L60 1) | `pyproject.toml`, README | `tests/test_run_config.py` |
| Secrets from env only; `.env` git-ignored; full-history secret scan | `config.py`, CI | gitleaks job in CI |

Every money, idempotency and access control above has a recorded break test: the
code was broken on purpose, the test failed, and the code was restored. See
`docs/progress/`.

## Known gaps and planned fixes

| Gap | Risk | Planned fix |
|---|---|---|
| **No end-user auth** (S3, L60 1). `X-Demo-User` is trusted. | Anyone who reaches the API can read any user's debts and file a "Not me" that cannot be undone. | Real sessions or JWT before any non-loopback use. Until then, run on `127.0.0.1` only. |
| **Transfer before commit** (S1, rest). The key stops a double debit on retry, but if the commit fails and the retry's safety net then skips the saving, money has moved with no ledger row. | Savings and bank disagree until someone reconciles by hand. | Transactional outbox (R4): commit the ledger row and a pending transfer together; a worker calls the bank with the same key. |
| **Push and platform signal have no worker** (S6). A crash after commit leaves the alert `pending`; a failed signal is retried only when the user taps again. | A missed alert, or a dispute the platform never hears about. | The R4 outbox worker with backoff and a timeout for each provider call. |
| **Platform call under the contract lock** (S4 trade-off). | A slow platform stalls that contract's webhooks. | The outbox (R4) moves the call out of the request. |
| **Monthly total in concurrent alerts** (S5). Two new debts at the same moment each leave out the other. | The L43 total in an alert is too low. | A per-user advisory lock for created events. |
| **No rate limits or quotas** (S11). `pending_parent` rows grow without limit; the summary has no pagination; no request timeout. | Resource exhaustion by a buggy or hostile platform. | Per-vendor rate limit, expiry for old pending events, pagination, server timeouts. |
| **Real deployment** | | TLS everywhere; secrets in a secret manager with rotation, including per-vendor webhook secrets; encryption at rest; PDPA: consent records, retention and deletion policy, a processing record, and a data subject request flow; central log redaction. |

## Running the security checks

From `backend/`:

```bash
uv run pytest -q tests/db/test_app_role.py tests/test_trusted_host.py \
  tests/webhooks/test_log_privacy.py tests/webhooks/test_bank_idempotency.py
uv run pytest -m concurrency -v              # races: idempotency, locks, disputes
uv export --frozen --no-emit-project --format requirements.txt -o /tmp/req.txt
uv run pip-audit -r /tmp/req.txt --strict --disable-pip
```

CI runs the whole suite as `lumen_app`, plus `pip-audit` and a full-history `gitleaks` scan.
