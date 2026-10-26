---
name: break-test
description: Prove critical Lumen tests (money, idempotency, invariants, security) can fail. For each one, break the code on purpose, confirm the test fails for the right reason, restore, and rerun green. Produces table rows for the progress log. Use after writing critical tests, before /session-finish.
argument-hint: "[test id or path ...]"
---

# Break test (CLAUDE.md Hard rule 4: break before trust)

Targets: $ARGUMENTS

If no targets were given, pick the critical tests added or changed on this branch:
1. Run `git diff main...HEAD --stat` and `git diff --stat`.
2. From that list, keep the tests that cover money, idempotency, invariants (INV-x), or security.

Run every command from `backend/`.

## Before the first break
1. Run `git status --porcelain`.
2. Every file you will break must have no uncommitted changes, so that `git diff` shows only the break and the restore is exact. If a target file has changes, commit them first or ask the user.

## For each case
1. **Break:** make the smallest change to **app code** that removes the behaviour the test protects. Examples: drop the idempotency check, change a clamp bound, remove a lock, compare with `<` instead of `<=`.
   - Never edit the test itself.
   - Never break the code by adding a float, a secret, or a brand name.
2. **Run** only that test with `uv run pytest <path>::<name> -x -q`.
3. **Confirm it fails for the right reason.** Read the assertion message or error.
   - A failure from an import error, a syntax error, or an unrelated fixture does not count. Fix the break and run again.
   - If the test **passes** while the code is broken, that is a blind spot. Restore the code first, then treat it as a bug under the CLAUDE.md bug procedure: reproduce, isolate, explain, fix the test, and break again. Record it under "Bugs found".
4. **Restore:** run `git checkout -- <file>`, or `git restore <file>`. Then run `git diff --exit-code -- <file>`; it must print nothing.
5. **Rerun** the same test. It must pass.

For a break in a migration:
1. Downgrade the test DB first, then upgrade with the broken migration. A DB already at head never reruns an edited migration.
2. After the restore, downgrade and upgrade again.

## After the last case
1. Run the full suite once: `uv run pytest -q`.
2. Run `git status --porcelain`. It must show no app-code changes left over from a break.

## Output
Return one row per case, ready for the progress log. Continue the B-number sequence from the latest progress log.

```
| # | What was broken | Test that failed | Restored and green |
|---|---|---|---|
| B22 | `app/rules/rules.json`: max saving 500.00 -> 5000.00 | `test_RE_04_large_item_capped` (got 2000.00, expected 500.00) | yes |
```

"Restored and green" is `yes` only when two checks passed: `git diff --exit-code` was clean, and the rerun passed. Otherwise write `no` and the reason.
