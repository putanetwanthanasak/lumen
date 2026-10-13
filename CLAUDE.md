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

## Locked decisions not yet reflected in docs/spec
- **L40** Until Oct 19, build core + tests only: Ledger, webhook, idempotency, auto-save, debt summary, new-debt alerts. No Payoff Planner, no AI, no polished frontend yet.
- **L41** The webhook contract carries full debt data. In addition to 04 section 5.3, the contract includes `min_payment`, `late_fee_per_period`, `monthly_rate`, and overdue status (`overdue_days`). All of this is an assumption about the platform API.
- **L42** "Not me" = installment becomes `disputed` + audit log entry + signal sent back to the platform via a mock provider + contact-channel info returned. Never claim the system stops the platform transaction.
- **L43** Every new-debt notification includes the user's current total monthly installment amount.
- Saving rule: 5% of item value, minimum 10 THB, maximum 100 THB per item. Never save a partial amount. Safety net: skip saving if the bank balance would drop below 500 THB (system-set, not user-configurable).
- Installment `kind`: `purchase`, `cash_withdrawal`, `cash_loan` (the last two never trigger saving).
- Python 3.14 locally and in CI. If a package does not support it, stop and report. Do not downgrade on your own.

## Hard rules
1. **Money uses `decimal.Decimal` and `Numeric(12,2)` only.** No floats anywhere, including tests.
2. **No secrets in code or git.** Read from env only. `.env` is in `.gitignore` from the first commit. Never print secret values in chat.
3. **Write tests together with code.** Test names reference IDs from 05, e.g. `test_RE_07_safety_net_skips_when_below_protected_min`.
4. **Break before trust:** for critical tests (money, idempotency, invariants), temporarily break the code, confirm the test fails, then restore. Record the result in the progress log.
5. **Never use the names or logos of KBank, KBTG, Kasikornbank, or Shopee** in code, UI, or mock data. Display name is "Lumen"; the mock vendor is "ShopDemo".
6. **Advisory only, never block:** the system never blocks a transaction or a savings withdrawal.
7. **Do not make spec decisions on your own.** If the spec is unclear or contradictory, choose the safest option, continue, and log it under "Open questions".
8. ORM or parameterized queries only. Never build SQL by string concatenation.
9. Verify every new package exists and is the intended one. Pin versions in a lock file.
10. Any Thai text (UI copy, notifications) must not use em dashes (—).
11. **Never push to `main`.** Work on a branch named by what it does (see Git workflow), push that branch, and open a PR with `gh pr create`. **Never merge the PR yourself.** The user reviews and merges.

## Git workflow
- Start of work: `git switch main && git pull`, then create a branch.
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
- PR description: what changed, test IDs covered, break tests performed, then a **Reading guide**:
  1. Files in the order to read them, tests first (they describe the behavior), one line each on what the file does.
  2. "Must read" vs "skim": money, SQL, transactions, migrations, and security are must-read; config and boilerplate are skim.
  3. For each must-read file, the specific functions or line ranges that matter and why.
  4. Two or three self-check questions the reader should be able to answer after reading (e.g. "What stops the same event from saving twice?").
- When the user leaves review comments on a PR, read them with `gh pr view --comments`, address each one, and reply to it.

## Definition of Done for every session
From `backend/`, all of these pass:
```
ruff check . && ruff format --check .
mypy app
pytest --cov=app
```
Then commit, push the session branch, open a PR, and wait for CI on the PR to go green. Do not end a session with red CI. Post the PR link in the final summary.

## Reporting
At the end of every session, append to `docs/progress/YYYY-MM-DD.md` under `## Session N: <name>`:
- Done (test IDs passing)
- Numbers: test count, Hypothesis generated cases, coverage
- Break tests performed and results
- **Deviations from docs/spec and why**
- **Open questions** for the user
- Carry-over work
