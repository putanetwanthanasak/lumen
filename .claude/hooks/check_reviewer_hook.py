"""Self-check for reviewer_readonly_bash.py.

Run from the repo root: python3 -I .claude/hooks/check_reviewer_hook.py

Exits 1 if any command is allowed or blocked wrongly. Not collected by pytest
(it lives outside backend/), so run it by hand after changing the hook.
"""

import json
import subprocess
import sys

H = ".claude/hooks/reviewer_readonly_bash.py"
allow = [
    "git diff main...HEAD",
    "git diff main...HEAD --stat",
    "git log --oneline main..HEAD",
    "git show HEAD:CLAUDE.md",
    "git log -p -3",
    "cd backend && uv run pytest -q",
    "cd backend && uv run pytest --cov=app 2>&1 | tail -30",
    "uv run ruff check .",
    "uv run ruff format --check .",
    "uv run mypy app",
    "grep -rn 'float(' backend/app",
    "sed -n '1,40p' CLAUDE.md",
    "sed -n '$p' x",
    "find backend -name '*.py'",
    "cat .env.example",
    "git branch --show-current",
    "grep -E 'a|b' x.py",
    "ls docs/spec",
]
block = [
    "rm -rf backend",
    "git checkout -- x",
    "git commit -m x",
    "git push origin HEAD",
    "git -c core.pager=sh log",
    "git diff --output=x",
    "uv run ruff check --fix .",
    "uv run ruff format .",
    "ruff format x.py",
    "sed -i 's/a/b/' x",
    "sed -n 's/a/b/w out' x",
    "sed -n '1p;e rm x' x",
    "echo hi > x",
    "cat x >> y",
    "git diff; rm x",
    "ls & rm x",
    "cat $(echo x)",
    "cat `echo x`",
    "echo $SECRET",
    "cat .env",
    "grep X backend/.env",
    "find . -delete",
    "find . -exec rm {} +",
    "python -c 'import os'",
    "uv pip install x",
    "uv run python -c 1",
    "sort -o x y",
    "git branch -D main",
    "tee x",
    "cp a b",
    "git stash",
    "(rm x)",
    "ls\nrm x",
]
bad = 0


def run(payload):
    return subprocess.run(  # noqa: S603 (fixed argv: this interpreter and the hook path)
        [sys.executable, "-I", H], input=json.dumps(payload), capture_output=True, text=True
    )


for c in allow:
    r = run({"tool_name": "Bash", "tool_input": {"command": c}})
    if r.returncode != 0:
        bad += 1
        print("SHOULD ALLOW:", repr(c), r.stderr.strip())
for c in block:
    r = run({"tool_name": "Bash", "tool_input": {"command": c}})
    if r.returncode != 2:
        bad += 1
        print("SHOULD BLOCK:", repr(c), r.returncode)
for p, want in [
    ("/home/pumon/Documents/Lumen/.env", 2),
    ("/x/.env.local", 2),
    ("/x/.env.example", 0),
    ("/x/CLAUDE.md", 0),
]:
    r = run({"tool_name": "Read", "tool_input": {"file_path": p}})
    if r.returncode != want:
        bad += 1
        print("READ WRONG:", p, r.returncode)
for path, want in [("/x/.env", 2), ("backend", 0)]:
    r = run({"tool_name": "Grep", "tool_input": {"pattern": "SECRET", "path": path}})
    if r.returncode != want:
        bad += 1
        print("GREP WRONG:", path, r.returncode)
print(f"{len(allow)} allow, {len(block)} block, 4 read and 2 grep cases; wrong: {bad}")
sys.exit(1 if bad else 0)
