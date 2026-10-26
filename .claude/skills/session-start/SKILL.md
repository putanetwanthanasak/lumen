---
name: session-start
description: Start a Lumen work session. Syncs main, reads the latest progress log, picks a branch name, and writes a plan with fixed headings, then stops for the user's approval before any code. Use at the start of every session, or with --dry-run to show the plan only.
argument-hint: "[--dry-run] <task description>"
---

# Session start

Task: $ARGUMENTS

If the arguments start with `--dry-run`, this is a **dry run**:
- Do not run any command that changes state: no `git switch`, `git pull`, or branch creation.
- Name the commands you would run.
- Read files as usual.
- Do steps 2 to 5, then stop.

## 1. Sync main (skip in a dry run)
1. Run `git status --porcelain`. If it shows anything, **stop**: tell the user what is uncommitted and ask what to do. Never stash or discard their work.
2. Run `git switch main`, then `git pull`. If the pull fails or is not a fast-forward, stop and report.

## 2. Read context
1. Find the newest file in `docs/progress/` (the latest date in its name). Read its last `## Session N` section.
2. From that section, note the open questions, carry-over work, and the session number. The next session is N+1.
3. If the task touches requirements, read the matching parts of `docs/spec/` (03 product, 04 architecture, 05 tests and invariants). The Locked decisions in `CLAUDE.md` override the spec.

## 3. Pick a branch name
Use `<type>/<short-kebab-topic>`, as in the CLAUDE.md Git workflow:
- types: `feat/`, `fix/`, `test/`, `chore/`, `ci/`, `docs/`;
- name the branch after what the change does, never the date.

If the task holds two separate units of work, name one branch per unit.

## 4. Write the plan
Use exactly these headings, in this order. Write "None" under a heading rather than leaving it out.

```
## Plan: <task in a few words>
Branch: <type>/<topic>

### Goal
One or two sentences: what will be true when this is done.

### Test IDs to add or change
- <ID from 05, e.g. RE-07>: <behaviour the test proves> (new | changed)
Tests are written together with the code (Hard rule 3). Mark which ones are
critical (money, idempotency, invariants) and get a /break-test.

### Files to touch
- <path>: <what changes>

### Estimated changed lines (excluding tests)
<number> lines, with a short breakdown per file. Lock files are excluded.

### Risks (money, idempotency, SQL, migrations, security)
- Money: ...
- Idempotency: ...
- SQL: ...
- Migrations: ... (any schema change also updates tests/db/test_schema_snapshot.py, Hard rule 12)
- Security: ...

### Open questions
- <question>: <safest default I will use if there is no answer> (Hard rule 7)
```

## 5. Size check
If the estimate is over about 400 changed lines (excluding tests and lock files):
- propose a split before any code is written;
- list each PR with its branch name, scope, and estimate;
- make each PR one coherent unit that can be reviewed on its own.

## 6. Stop and wait
End the turn with the plan and the question "Approve this plan?" Do not create the branch, edit files, or write code until the user approves.

Once the plan is approved (never in a dry run):
1. Run `git switch -c <branch>`.
2. Build, writing tests together with the code.
3. Run /break-test for the critical tests.
4. Finish with /session-finish.
