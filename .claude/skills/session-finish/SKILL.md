---
name: session-finish
description: Finish a Lumen work session. Runs the Definition of Done, gets an independent review from the independent-reviewer subagent (at most 2 rounds), writes the progress log, commits, pushes the branch, opens the PR with a Reading guide, and waits for green CI. Use only when the planned work is built and its tests are written.
argument-hint: "[session name]"
---

# Session finish

Session name: $ARGUMENTS

Do the steps in order. Do not skip a step or reorder them.

## 0. Preconditions
1. Run `git branch --show-current`. It must not be `main` (Hard rule 11). If it is `main`, stop and ask.
2. Critical tests (money, idempotency, invariants, security) added or changed on this branch must have /break-test rows. If any are missing, run /break-test first.

## 1. Definition of Done
Run each command from `backend/`. All three must pass:

```
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest --cov=app
```

- If a check fails, follow the CLAUDE.md bug procedure: reproduce, isolate, explain, then fix and prove.
- Never retry blindly, loosen an assertion, add a sleep, or skip a test.
- Note these numbers for the log:
  - the test count;
  - the coverage %;
  - the Hypothesis generated cases, if the count changed. Use the method from the latest progress log.

## 2. Commit the work
- Commit everything for this session on the branch, so the reviewer can see it in `main...HEAD`.
- Use a typed message, for example `feat: ...`, ending with the attribution line from the system reminder.
- Do not push yet.

## 3. Independent review (at most 2 rounds)
1. Pick the spec files that match what the diff touches:
   - `docs/spec/03_product_spec.md` for product behaviour or UI copy;
   - `docs/spec/04_architecture.md` for the data model, the webhook contract, or the processing flow;
   - `docs/spec/05_testing_quality.md` for invariants or test IDs.
   Docs and config only means none.
2. Invoke the subagent with the Agent tool, `subagent_type: "independent-reviewer"`. The prompt must be **exactly** this template and nothing more:

   ```
   Review branch <branch> against main.
   Spec files to read: <paths, or "none">.
   ```

   - Do **not** add your summary, your reasoning, what you tested, what you think is risky, or what you already fixed. The reviewer must form its own view from the diff, CLAUDE.md, and the spec.
   - If the reviewer type is not available in this session, stop and tell the user. Do not use another agent type in its place, because that agent would not be read-only.
3. For each finding, either:
   - **fix it.** A real bug goes through the bug procedure, with a test that fails for that cause. A critical fix also gets a /break-test row. Commit the fix.
   - **or write why not.** Examples: a false positive, with the code line that shows it; out of scope, with the carry-over item; or a Locked decision that overrides it.
4. Rerun step 1 after any fix.
5. **Round 2:** if round 1 had any high or medium finding that you fixed, invoke a **fresh** reviewer with the same two-line template. Fix or explain its findings the same way.
6. **Stop:** never start a third round. If any high or medium finding is still open after round 2, stop and ask the user. List each open finding and why it is still open. Do not push until they answer.

## 4. Progress log
Append to `docs/progress/<today YYYY-MM-DD>.md`. Create the file with `# Progress: <date>` if it does not exist. Add this section:

```
## Session N: <name>

### Done
- <what was built> (test IDs passing)

### Numbers
- Tests: <count> passed (<count at start of session> at the start)
- Hypothesis: <generated cases>
- Coverage: <%> of app

### Break tests
| # | What was broken | Test that failed | Restored and green |
|---|---|---|---|
(rows from /break-test)

### Bugs found
(bug, root cause, proving test; or "None")

### Independent review: findings and how each was handled
Round 1 (`independent-reviewer`, <short sha reviewed>):
| # | Severity | Finding (file:line) | How it was handled |
|---|---|---|---|
| F1 | medium | ... | Fixed in <sha>; proved by `test_...` / Not fixed: <why> |
Round 2: (same table, or "Not needed: round 1 had no high or medium findings")

### Deviations from docs/spec and why
### Open questions
### Carry-over
```

Rules for the log:
- Write "None" under any empty heading.
- Session N is the last session number in `docs/progress/` plus 1.
- Commit the log.

## 5. Push and open the PR
1. Push in a Bash call of its own: `git push -u origin <branch>`. Never chain `git push` with `&&` or `;`, because the deny rule blocks it. Never push to `main`.
2. In a **separate** call, run `gh pr create --base main --title "<type>: <summary>" --body-file <file in the scratchpad>`. The body has these parts:
   - **What changed:** short bullets.
   - **Tests:** the test IDs covered, the counts, coverage, and ruff and mypy clean.
   - **Break tests:** the table.
   - **Independent review:** the number of findings per round, and how each was handled. One line each.
   - **Reading guide:**
     1. Files in the order to read them, tests first, one line each on what the file does.
     2. Mark each file **Must read** or **Skim**. Money, SQL, transactions, migrations, and security are must-read. Config and boilerplate are skim.
     3. For each must-read file, the functions or line ranges that matter, and why.
     4. Two or three self-check questions, for example "What stops the same event from saving twice?"
   - The PR attribution line from the system reminder.
3. Never merge the PR (Hard rule 11). The user reviews and merges.

## 6. Wait for CI
1. Run `gh pr checks <number> --watch`.
2. If a check is red:
   - read the log with `gh run view <id> --log-failed`;
   - follow the bug procedure, fix, and commit;
   - push again in a call of its own;
   - watch again.
3. Never end a session with red CI.

## 7. Final summary
Tell the user:
- the PR link;
- the test count and coverage;
- the break tests;
- the review findings and how each was handled;
- the open questions.
