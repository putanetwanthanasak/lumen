# Lumen: Context for Claude Code

Concept prototype for KBTG Kampus Hackathon 2026, Track 1 (Software Engineering & Quality).
The system receives BNPL debt webhooks from external platforms (simulated), builds an Installment Ledger, auto-saves on each purchase, alerts on every new debt, and (later) plans debt payoff.
Solo developer. Judging criteria: what was built, how it was developed, and **how it is tested and quality-assured**.

## Reference docs (read when relevant, not every time)
Spec docs are written in Thai. Read them for requirements; write everything you produce in English.
- `docs/spec/03_product_spec.md`: product spec and edge cases
- `docs/spec/04_architecture.md`: stack, folder layout, data model, webhook contract, processing flow
- `docs/spec/05_testing_quality.md`: invariants (INV-x) and test cases (RE-x, WH-x, ID-x, ...)
- `docs/progress/`: daily logs. Read the latest file before starting any session.
- `docs/api/kidnee-endpoints.md`: the API the KidNee screens use, with exact JSON. Update it with any change to those endpoints.
- Test ID families not yet in 05 (defined in the progress logs and the test docstrings): AF, NM, BF, PD, LO (Session 13); AS, CO (Session 14); UI-01 to UI-32 (frontend, Session 14-UI), UI-33 to UI-45 (Sessions 14-UI and 15-UI), UI-46 to UI-51 (frontend on the real API: buffer states, buffer move per month, months screen, personas, wiring, no money arithmetic in screens; Session 17); DM `/debts/months`, SM suggested monthly, PV preview saving, BS buffer shortfalls, and NT-08 to NT-10 `GET /notifications` (Session 15A, after 05's NT-01 to NT-07).

## Locked decisions not yet reflected in docs/spec
- **L40** Until Oct 19, build core + tests only: Ledger, webhook, idempotency, auto-save, debt summary, new-debt alerts. No Payoff Planner, no AI, no polished frontend yet.
- **L41** The webhook contract carries full debt data. In addition to 04 section 5.3, the contract includes `min_payment`, `late_fee_per_period`, `monthly_rate`, and overdue status (`overdue_days`). All of this is an assumption about the platform API.
- **L42** "Not me" = installment becomes `disputed` + audit log entry + signal sent back to the platform via a mock provider + contact-channel info returned. Never claim the system stops the platform transaction.
- **L58** Product core is one sentence: "See every BNPL debt the moment it happens, including the ones you did not make." Two outcomes: protection (alert on every new debt, strong alert for cash, "Not me" per L42) and saving. "Not me" is core scope, not optional. Payoff Planner and AI are roadmap only.
- **L43** Every new-debt notification includes the user's current total monthly installment amount.
- **L46 + L52** *(superseded by L63 on 2026-10-26; kept for history)* Saving rule is fixed and not user-configurable: **10%** of item value, minimum **10 THB**, maximum **500 THB** per purchase (hard limits). This replaces the 5% / 100 THB rule that appears in docs/spec and older tests. Never save a partial amount. Safety net: skip saving if the bank balance would drop below 500 THB. Users can only turn auto-save on or off and give consent. This supersedes 03 and the per-user rate/cap in 04 section 4.5.
- **L47** Idempotency key is `(vendor, event_id)`, not `event_id` alone.
- **L48** Late fees live in a separate `late_fees_accrued` column. INV-6 is `paid_amount <= principal + fee_total + late_fees_accrued`.
- **L49** Webhook money must be a JSON string with at most 2 decimal places. JSON numbers and extra decimals are rejected with 422, never rounded (single policy for WH-05).
- **L55** Webhook contract details: overdue events carry the *cumulative* late fee (set the value, never add a delta); `kind` must match the event type; `overdue_days` is required; signatures are lowercase hex only; same `(vendor, event_id)` with a different payload returns 409 and writes audit; bodies over 64 KB return 413 before signature checking; any text field with control characters U+0000 to U+001F returns 422.
- **L59** Session 8 open questions, answered: (1) a resend of a rejected event returns 409 again, the same answer as its first delivery; (2) a payment on a cancelled installment is recorded and the status stays `cancelled`; (3) cancel may move `disputed` to `cancelled`, but the dispute history must never be lost: keep `disputed_at` and the audit rows, so the UI can show "cancelled after you reported it"; (4) a cancel that arrives before its created event does not skip the saving; (5) a late fee after `paid_off` reopens the installment, and a fee drop below what was already paid is rejected, never clamped; (6) R2 bounds: months and installment_no ≤ 600, overdue_days ≤ 36,500; (7) two overdue events with the same `occurred_at`: the later delivery wins (contract assumption: timestamps are unique per contract).
- **L60** Session 9 open questions, answered: (1) no end-user auth before Oct 20: keep `X-Demo-User` (04 §9), run uvicorn on 127.0.0.1 only, document it as a known limitation; (2) "Not me" stores the platform signal status (`sent` / `failed`) and words the message from it, never claiming the report was sent when it was not; (3) messages: sent = "บันทึกการแจ้งของคุณแล้ว และส่งเรื่องให้ ShopDemo ตรวจสอบแล้ว Lumen ยกเลิกรายการแทนคุณไม่ได้ โปรดติดต่อ ShopDemo โดยตรงเพื่อยืนยันว่าไม่ใช่รายการของคุณ", failed = "บันทึกการแจ้งของคุณแล้ว แต่ยังส่งเรื่องให้ ShopDemo ไม่สำเร็จ Lumen ยกเลิกรายการแทนคุณไม่ได้ โปรดติดต่อ ShopDemo โดยตรงโดยเร็ว"; (4) 422 keeps `loc`; (5) 422 without a money reason is fine for now; (6) push backoff and a retry worker go with the R4 outbox after Oct 20; (7) no undo for "Not me".
- **L50** `cash_withdrawal` and `cash_loan` both get the strong alert (05 SV-03a).
- **L62** Manual entry: the user records an installment via the API (`X-Demo-User`), with item price, months, monthly amount, first due month and kind. Recording it adds it to the Ledger and auto-saves by the user's rule. The webhook path and "Not me" stay in the code, untouched and tested; they are not part of the new demo. Do not delete them.
- **L63** Saving rule: the user chooses exactly ONE mode, never combined. (a) percent: integer 1-100 of the item price, quantized to 0.01 with ROUND_DOWN; a result of 0.00 is skipped. (b) fixed: an amount per recorded installment, > 0, at most 2 decimal places (L49 money rules: JSON string, never rounded). No minimum and no per-purchase cap. Safety net stays: skip the whole saving if the bank balance would drop below 500 THB (exactly 500 is allowed). Never save a partial amount. `cash_withdrawal` and `cash_loan` never save. Saving still happens when the installment is unaffordable (advisory only, never block). The webhook path uses the same user setting (Session 12, open question 1). Supersedes L46 + L52.
- **L64** Budget warning: if the monthly installment budget > income / 3, settings are still saved (200/201) and the response carries the warning code `BUDGET_ABOVE_ONE_THIRD_OF_INCOME`. Compare as `budget * 3 > income` with Decimal (no division); exactly one third gives no warning. Source: Bank of Thailand financial-literacy guidance (total debt payments should not exceed one third of monthly income). It is guidance, not a regulation.
- **L65** Affordability verdict (Session 13), per calendar month over the candidate's term (its first due month for `months` months). Month total = the monthly amounts of every counted installment due that month + the candidate. RED if any month has `total * 3 > income` (Bank of Thailand financial-literacy guidance: total debt payments should not exceed one third of monthly income; guidance, not a regulation); else YELLOW if any month has `total > monthly_installment_budget`; else GREEN. Decimal only, no division; exactly one third is not RED, exactly the budget is not YELLOW. Counted: the L43 owed set (active or disputed, something left to pay), full monthly amount in every scheduled month. No settings: 409 `SETTINGS_REQUIRED`, never a guessed income. Advice only: recording succeeds for every verdict.
- **L66** Buffer = the user's savings balance. Moving buffer money back to the main account is always the user's own action, never automatic, and never blocked (an amount above the balance is a 422, not a block).
- **L67** Leftover saving on payday: if `leftover_saving_enabled` and auto-save is on with consent, save `budget - month total` when it is > 0. Same 500 THB safety net, all or nothing. At most once per user per month.
- **L68** "Not me" is rejected on `vendor='manual'` installments: 409 `NOT_ME_UNAVAILABLE_FOR_MANUAL_ENTRY`, no platform signal, no status change, an audit row per attempt.
- **L69** No prepayment advice. BNPL apps mostly cannot be paid early, so the payoff assistant never ranks which debt to pay off first. L69 to L72 bring the payoff assistant's numbers (GET /assistant/plan, no AI) into scope; this supersedes the "Payoff Planner ... roadmap only" part of L58 for those numbers, the ranking tests PP-01 to PP-07 in 05 section 4.10, and the "do not recommend loans" line in 03 section 4 for the L70 consolidation estimate. AI stays roadmap only.
- **L70** Consolidation eligibility, all must hold: (a) the upcoming month totals (from the current month) contain a run of >= 3 consecutive months over budget; (b) the estimated consolidated payment brings every month total back within budget and makes no month RED (`total * 3 > income`, L65; Session 14 open question 14), checked on the plan's estimate and again on the payoff amounts the request names (open question 15); (c) no counted installment is overdue; (d) no counted installment is `disputed` (Session 14, open question 4: never pay off a debt the user reported as "Not me"). Otherwise the plan says it is not needed or not worth it, and no button.
- **L71** The bank decides with its own data. User-entered numbers start a consolidation request but never approve it. The mock bank decision is a provider interface with a mock implementation, like the bank provider.
- **L72** An approved consolidation creates a new installment kind `consolidation_loan` in the Ledger. It never triggers saving, counts in month totals and in "คิดก่อน" (the L65 preview), and "Not me" is rejected on it (like L68). The paid-off installments get the status `consolidated`; their history is kept, never deleted. A manual entry can be consolidated; its payout goes to an unnamed platform (`unnamed_platform`, never "manual") until the user names the app (`platform_name`, open question 16).
- **L73** One-server demo (Session 15A): the browser always calls `/api/...`. In dev, Vite proxies `/api` and strips the prefix; in the demo, `app.serve.create_serving_app` mounts the unchanged API app at `/api` and `frontend/dist` at `/`, behind the same TrustedHost list. The API's own routes stay at the root. It runs only through `python -m demo.kidnee serve`, on 127.0.0.1, against its own `lumen_kidnee` database (never `lumen`). Never bind 0.0.0.0. Tests: KD-01 serving, KD-02 loopback only, KD-03 database whitelist and `--yes`, KD-04 the seeded personas and the served database, KD-05 one story per persona (`demo-mon` in budget, `demo-over` covered by the buffer, `demo-consolidate` eligible for consolidation and not covered; Session 17).
- **L51** INV-5 and "auto-save user = event user" are enforced in the service and checked in `reconcile.assert_user_invariants()`, not by DB triggers or composite FKs.
- Installment `kind`: `purchase`, `cash_withdrawal`, `cash_loan`, and from L72 `consolidation_loan` (every kind but `purchase` never triggers saving).
- Python 3.14 locally and in CI. If a package does not support it, stop and report. Do not downgrade on your own.

## Hard rules
1. **Money uses `decimal.Decimal` and `Numeric(12,2)` only.** No floats anywhere, including tests.
2. **No secrets in code or git.** Read from env only. `.env` is in `.gitignore` from the first commit. Never print secret values in chat.
3. **Write tests together with code.** Test names reference IDs from 05, e.g. `test_RE_07_safety_net_skips_when_below_protected_min`.
4. **Break before trust:** for critical tests (money, idempotency, invariants), temporarily break the code, confirm the test fails, then restore. Record the result in the progress log.
5. **Never use the names or logos of KBank, KBTG, Kasikornbank, K PLUS, or Shopee** in code, UI, or mock data, or any wording that implies the prototype is an official bank service. Display name is "KidNee (คิดหนี้)" (Session 15A); "Lumen" stays the repo and code name. The mock vendor is "ShopDemo".
6. **Advisory only, never block:** the system never blocks a transaction or a savings withdrawal.
7. **Do not make spec decisions on your own.** If the spec is unclear or contradictory, choose the safest option, continue, and log it under "Open questions".
8. ORM or parameterized queries only. Never build SQL by string concatenation.
9. Verify every new package exists and is the intended one. Pin versions in a lock file.
10. Any Thai text (UI copy, notifications) must not use em dashes (—).
11. **Never push to `main`.** Work on a branch named by what it does (see Git workflow), push that branch, and open a PR with `gh pr create`. **Never merge the PR yourself.** The user reviews and merges.
12. **Any schema change updates `tests/db/test_schema_snapshot.py` in the same PR**, and every new migration is checked by the snapshot test, not only by `alembic check` (which misses CHECK expressions and partial-index WHERE clauses).

## When a test fails unexpectedly or a bug appears
Find the root cause before changing code. Never retry, loosen an assertion, add a sleep, or skip a test to make it pass.
1. **Reproduce:** get a reliable failing case. For flaky or concurrency failures, run the test repeatedly (e.g. 20 times) and record how often it fails.
2. **Isolate:** narrow it to the smallest input, test, or code path that still fails. Check recent changes first (`git diff main`).
3. **Explain:** state the root cause in one or two sentences, with evidence (log line, query, failing value). If you cannot explain it, keep investigating; do not fix.
4. **Fix and prove:** write or keep a test that fails for this exact cause, apply the smallest fix, show the test now passes, and run the full suite.
Record the bug, its root cause, and the proving test in the progress log under "Bugs found".

## Session workflow
Every session runs: plan -> build -> self-check -> independent review -> summary.
- **Start:** `/session-start <task>` syncs main, reads the latest progress log, and writes the plan. Then it waits for approval.
- **Critical tests:** `/break-test` covers money, idempotency, and invariants (Hard rule 4).
- **Finish:** `/session-finish` runs the Definition of Done (`ruff check`, `ruff format --check`, `mypy app`, and `pytest --cov=app`, from `backend/`). It gets a review from the read-only `independent-reviewer` subagent and writes the progress log (Reporting format). Then it pushes, opens the PR with its Reading guide, and waits for green CI. Never end a session with red CI.
- **Review comments:** `/pr-comments <PR>`.

The skills live in `.claude/skills/`, and the subagent in `.claude/agents/`.

## Git workflow
- Branch name: `<type>/<short-kebab-topic>` describing the function of the change, not the date. Types:
  - `feat/` new behavior (e.g. `feat/saving-rule-engine`, `feat/webhook-receiver`)
  - `fix/` bug fix (e.g. `fix/duplicate-auto-save`)
  - `test/` tests only (e.g. `test/idempotency-concurrency`)
  - `chore/` tooling, config, dependencies (e.g. `chore/repo-setup`)
  - `ci/` CI workflow changes
  - `docs/` documentation only
- One branch = one coherent unit of work = one PR. A session may produce more than one PR if it covers separate units.
- Commit messages follow the same types: `feat: add compute_saving with min/max clamp`.
- CI runs on `pull_request` and on `push` to `main`.
- Keep each PR small enough to read in about 30 minutes: aim for under ~400 changed lines excluding tests and lock files. Split otherwise.
- PR description: its format and the Reading guide are defined in `/session-finish`.
- Review comments on a PR: use `/pr-comments`.

## Definition of Done and Reporting
- **Definition of Done:** all checks pass and CI is green on the PR. The steps are in `/session-finish`.
- **Reporting:** the progress log format, in `docs/progress/YYYY-MM-DD.md`, is also in `/session-finish`. It includes the independent review findings and how each was handled.
