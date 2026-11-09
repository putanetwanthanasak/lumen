# Public release audit (2026-11-09)

Scope: the whole repository before it becomes public: every commit on every ref
(local branches, remote branches, tags; 319 commits, 109 refs), the tracked files
at `main` `f95fcd6`, the working tree, and this PR's own files (the README, this
report, four screenshots), rescanned on the branch. Nothing was deleted and no history
was rewritten. This audit only reports.

## Recommendation

The three options considered:
- **(a)** make this repository public as is;
- **(b)** first clean specific files in a commit (only if the history itself is harmless);
- **(c)** publish a fresh public repository from a squashed snapshot (if anything sensitive is in history).

**(a) Make this repository public as is, after this PR merges.** (b) is not needed: no
file has to change before release. (c) is not needed for safety. The history holds no
secrets, no third-party personal data, and no large or generated files. Every finding
below is low risk except one rated low to medium (finding 11, a screen's look), and none
needs a history rewrite. No secret ever reached git, so no
key has to be rotated because of this release.

One decision is yours: every commit carries the owner's name and personal email
(finding 5). That is normal for a portfolio. If you do not want that email public,
only option (c), a fresh repository from a squashed snapshot with a GitHub noreply
author, removes it from history.

## How it was checked

| Check | Command or method | Result |
|---|---|---|
| Secrets, full history | gitleaks 8.30.1 (the version CI pins), offline: `gitleaks detect --log-opts="--all"`, then again with `--log-opts="--all -m"` so merge commits are scanned too | 252 non-merge commits, then all 319 commits: **0 findings** |
| Secrets, working tree | `gitleaks dir .` | 4 findings, all in untracked, git-ignored files (finding 2) |
| Secrets, this PR | `gitleaks dir .` on the branch after the README and this report were written; `gitleaks detect --log-opts="main..docs/public-readme"` | No finding in any file this PR adds (the same 4 working-tree hits as above, nothing else) |
| Secrets, CI | the `gitleaks` job on every push to `main` (latest: run 42561485817, 2026-11-09) | 225 commits on `main`, 0 findings |
| `.env` ever committed | every path in every commit (`git log --all --name-only`, `git rev-list --all --objects`) | Never. Only `.env.example`, whose 7 versions hold empty or example values only |
| Personal and brand data | a scan of every blob ever committed and every commit message for home paths, emails, Thai phone numbers, IP addresses, bank and shop names, competition words, "official" wording | Findings 5 to 12 |
| Large and generated files | `git cat-file --batch-check` over all objects; a path scan for build output, caches, media | None (findings 13 and 14) |

No secret value was printed or written anywhere during the audit; gitleaks ran with
`--redact`.

## Findings

| # | Finding | Where | Risk | Recommendation |
|---|---|---|---|---|
| 1 | No secret in any commit, merges included | all 319 commits, 109 refs | None | Nothing to do. Keep the CI gitleaks job. |
| 2 | Working-tree scan hits: 3 `generic-api-key` in `.env`, 1 false positive in a mypy cache file | `.env`, `.mypy_cache/` (both untracked and git-ignored) | None for the repo | Keep `.env` out of git (`.gitignore:2`). Nothing in git to rotate. |
| 3 | `.env` was never committed; `.env.example` never held a real value | `.env.example`, 7 versions | None | Nothing to do. |
| 4 | The spec documents are local only (`docs/spec/` is git-ignored because they name third parties) and were never committed. CLAUDE.md, DESIGN.md and the logs still cite `docs/spec/03..05` | `.gitignore:7`, `CLAUDE.md`, `DESIGN.md`, `docs/progress/` | Low: dangling references for a reader, nothing leaked | The new README says the spec documents are not published. |
| 5 | Every commit's author is the owner: 264 as "Putanet Wanthanasak", 55 GitHub web merges under the GitHub display name (the same as the Linux username in finding 7), all with the owner's personal Gmail address | commit metadata | Low: the owner's own name and email become public | Acceptable for a portfolio. To hide the email in history, choose (c) with a noreply author. Either way, turn on GitHub's "Keep my email addresses private" for future web commits. |
| 6 | The owner's GitHub username and the repo's earlier name (`buffer`) | `docs/progress/2026-10-13.md` | Low: the owner's own | Keep. |
| 7 | A local path with the Linux username, `/home/<user>/Documents/Lumen-design` (this report does not repeat the username) | `docs/progress/2026-10-27-ui-design.md:5`; in history also `/home/<user>/Documents/Lumen/.env` as a test input in `.claude/hooks/check_reviewer_hook.py` (added in `6fb28b5`, removed in `4916be7`) | Low: reveals a username only | Optional: change the one line to `~/Documents/Lumen-design` in a later docs commit. The history copies are harmless. |
| 8 | No third-party personal data: no other person's name, email or phone number, no screenshots of real posts. At `f95fcd6`, the only image ever committed is the app's own `frontend/public/favicon.svg`; this PR adds four PNG screenshots of mock data (`docs/images/`), checked: no text or EXIF chunks, only `IHDR`, `IDAT`, `IEND`. Personas are fictional (`demo-mon`, "ม่อน"); the only IP is a private test value (`backend/tests/test_trusted_host.py`). Email matches were file names such as `@2x.png` | all blobs | None | Nothing to do. |
| 9 | Bank and shop brand names: **none in code, UI, mock data or tests at `main`**. Guards build the names from parts so the files do not hold them (`backend/app/ai/grounding.py:142-144`, `backend/tests/notifications/test_copy.py:130`). In docs they appear as the rule against using them and as grep reports, with two exceptions that name the competition's organizer: `CLAUDE.md:3` and, from this PR, the README's "Context" section (one mention, as the owner instructed; finding 10). Earlier versions of the guard code and tests held the names literally as deny-list entries | `CLAUDE.md` (rule 5 and line 3), `README.md` ("Context", from this PR), `.claude/agents/independent-reviewer.md`, `docs/progress/2026-10-13.md`, `2026-10-16.md`, `2026-10-18.md`, `2026-10-27-ui-design.md`, `docs/reviews/2026-10-15-review-gate.md`; history of the guard files | Low: no mention is branding; the rule text says *not* to use the names, and the two competition mentions state a fact | Keep. Rewriting the docs would not remove them from history; only (c) does. |
| 10 | The competition is named, and its public judging criteria quoted, in the instructions file; the README names it once in "Context", as instructed. Other mentions are generic: "a 2026 hackathon (Track 1)", the UI footer "Concept prototype สำหรับการแข่งขัน", the package description. No notes on judges, other teams or pitch tactics were found; the logs mention a mentor session and a deck deadline only | `CLAUDE.md:3-5`, `README.md` ("Context"), `DESIGN.md:3`, `frontend/src/copy.ts:12`, `backend/pyproject.toml:4` | Low | Keep. |
| 11 | The `#/account` host screen looks like a generic bank-app home (deep green-teal, a passbook card, a masked number `xxx-x-x1234-x`). It has no name or logo, says "ข้อมูลจำลองสำหรับเดโม", every extra button says it is an example, and the footer says concept prototype | `frontend/src/screens/Account.tsx`, `frontend/src/components/HostScreen.tsx`, `DESIGN.md` 7.7 | Low to medium: a screenshot out of context could read as a real bank app | Code unchanged, as instructed. The README does not show this screen and carries the disclaimer. Do not post this screen without the disclaimer. |
| 12 | The Bank of Thailand is cited for its public one-third-of-income guidance | `frontend/src/copy.ts`, `backend/app/ai/grounding.py`, `backend/app/ai/prompts/summary_v2.md`, DESIGN.md, docs | Low: always worded as guidance ("ธปท. แนะนำ"), never as endorsement, and tested (AI-30, the grounding check) | Keep. |
| 13 | No large file: no blob over 1 MB in any commit. The largest tracked file is `backend/uv.lock` (272 KB) | all objects | None | Nothing to do. |
| 14 | No generated file was ever committed: no `dist/`, `node_modules/`, `__pycache__`, coverage, `.hypothesis`, `.test-build` or video, and no image other than the favicon until this PR's four screenshots (finding 8). The lock files are tracked on purpose (rule 9) | all paths in history | None | Keep the 61-second demo video out of git, as planned. |
| 15 | The AI workflow is public: `CLAUDE.md`, `.claude/skills/`, `.claude/agents/`, `.claude/hooks/`, `.claude/settings.json` (deny rules for pushing to `main`) | `.claude/`, `CLAUDE.md` | None: no secrets, and no local paths at `main` | Keep. The README explains how Claude Code was used. |
| 16 | No LICENSE file. A public repository without one is "all rights reserved": people can read it but have no right to reuse it | repo root | Open question | Choose a license (or none) before or after going public. Not added here, as instructed. |

## What changes when the repository is public
- **Branch protection becomes available on the free plan** (`docs/progress/2026-10-13.md` notes it was not available while private). Protect `main`: require a PR, require the four CI checks, block force pushes.
- **CI on fork PRs** runs with a read-only token and no secrets. The workflow uses no secrets (its Postgres credentials are throwaway values for a CI container), so nothing changes.
- **GitHub secret scanning and push protection** are free for public repositories; turn them on as a second guard next to gitleaks.
