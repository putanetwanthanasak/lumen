---
name: pr-comments
description: Handle the user's review comments on a Lumen PR. Reads every comment, addresses each one in code or in a reply, replies to each, pushes, and re-runs the Definition of Done. Use when the user says they left comments on a PR.
argument-hint: "[PR number]"
---

# PR comments

PR: $ARGUMENTS. If no number is given, use the PR for the current branch: `gh pr view --json number -q .number`.

## 1. Read every comment
Read the comments from three places:
- `gh pr view <n> --comments` for the conversation comments;
- `gh api repos/{owner}/{repo}/pulls/<n>/comments` for the inline review comments, each with its `id`, `path`, `line`, and `body`;
- `gh api repos/{owner}/{repo}/pulls/<n>/reviews` for review summaries.

Then:
1. Make a numbered list of every comment that asks for something or asks a question. Skip your own earlier replies.
2. Switch to the PR's branch: `gh pr view <n> --json headRefName -q .headRefName`, then `git switch <branch>` and `git pull`.

## 2. Address each comment
Handle each comment in its own way:
- **A change request:**
  - make the change, keeping the Hard rules in force;
  - if it is a bug, follow the CLAUDE.md bug procedure, with a test that fails for that cause;
  - if it touches money, idempotency, or invariants, add a /break-test row;
  - if it changes the schema, update `tests/db/test_schema_snapshot.py` (Hard rule 12).
- **A question:** answer it plainly, with the file and line that show the answer.
- **A spec decision:** if the comment decides something the spec left open, apply it.
  - Note it for the user as a candidate Locked decision.
  - Do not edit the Locked decisions in CLAUDE.md unless the user asks.
- **A disagreement:** if you think the request would break a Hard rule or a Locked decision, do not apply it. Reply with the rule and the reason, and leave it for the user.

Commit in small typed commits, for example `fix: ...` or `test: ...`, each ending with the attribution line from the system reminder. One commit may address several related comments.

## 3. Definition of Done
Run each command from `backend/`. All three must pass:

```
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest --cov=app
```

## 4. Push
Push in a Bash call of its own: `git push`. Never chain `git push` with `&&` or `;`, and never push to `main`.

## 5. Reply to each comment
Reply only after the push, so every commit SHA in a reply already exists on GitHub.
- For an inline comment, reply in its thread: `gh api repos/{owner}/{repo}/pulls/<n>/comments/<comment id>/replies -f body='...'`.
- For a conversation comment, run `gh pr comment <n> --body '...'` and quote the comment it answers.
- Each reply says what changed and in which commit SHA, or answers the question, or explains why nothing changed.
- Keep replies short. Write a bare `@name` only for a real login you mean to notify.

## 6. Wait for CI
1. Run `gh pr checks <n> --watch`.
2. If a check is red, fix it with the bug procedure and push again.
3. Never merge the PR.

## 7. Progress log
Append to today's `docs/progress/` file, under the current session:
- a short "PR #<n> review comments" list: each comment, then what was done;
- any new break-test rows.

Commit the log and push it in a call of its own.

## 8. Summary
Tell the user:
- each comment and how it was handled;
- the commit SHAs;
- the CI status.
