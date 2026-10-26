"""Self-check for reviewer_readonly_bash.py.

Run: python3 -I .claude/hooks/check_reviewer_hook.py (CI runs it on every PR).

Each case feeds the hook the JSON Claude Code sends and checks the exit code:
0 allows the tool call, 2 blocks it. Exits 1 if any case is wrong.
"""

import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reviewer_readonly_bash.py")

ALLOW = [
    "git diff main...HEAD",
    "git diff main...HEAD --stat",
    "git log --oneline main..HEAD",
    "git show HEAD:CLAUDE.md",
    "git log -p -3",
    "git log --oneline -1 'HEAD~3'",
    "git branch --show-current",
    "cd backend && uv run --locked pytest -q",
    "cd backend && uv run --locked pytest --cov=app 2>&1 | tail -30",
    "uv run --locked pytest -q -k 'saving and not cash' tests/rules/test_engine.py",
    "uv run --frozen pytest -x --tb=short -rA",
    "uv run --locked ruff check .",
    "uv run --locked ruff check --select E501 .",
    "uv run --locked ruff format --check .",
    "uv run --locked mypy app",
    "grep -n 'float(' backend/app/money.py",
    "grep -E 'a|b' x.py",
    "git diff main...HEAD | grep -n 'float' | sort -u | uniq -c",
    "sed -n '1,40p' CLAUDE.md",
    "sed -n '$p' x",
    "find backend -name '*.py'",
    "cat .env.example",
    "grep -n 'x#y' CLAUDE.md",
    'grep -n "a b" CLAUDE.md',
    "sed -n '1,5p' 'docs/progress/2026-10-18.md'",
    "ls docs/spec",
]
BLOCK = [
    # Writes, deletes, and git state changes.
    "rm -rf backend",
    "cp a b",
    "tee x",
    "git checkout -- x",
    "git commit -m x",
    "git push origin HEAD",
    "git stash",
    "git branch -D main",
    "git -c core.pager=sh log",
    "git diff --output=x",
    "git diff --outp=x",
    "git log --ext-diff",
    # Shell syntax that writes, chains, or expands.
    "echo hi > x",
    "cat x >> y",
    "git diff; rm x",
    "ls & rm x",
    "(rm x)",
    "ls\nrm x",
    "cat $(echo x)",
    "cat `echo x`",
    "echo $SECRET",
    "cat ~/.ssh/id_rsa",  # blocked by the tilde rule; the home-directory rule is below
    # Linters and tests: only options that cannot write (review round 1, F2 and F3).
    "uv run --locked ruff check --fix .",
    "uv run --locked ruff format .",
    "ruff format x.py",
    "uv run --locked ruff check -o ../CLAUDE.md .",
    "uv run --locked ruff check --output-file=../CLAUDE.md .",
    "uv run --locked ruff check --config 'fix = true' .",
    "uv run --locked pytest --basetemp=app",
    "uv run --locked pytest --junitxml=../CLAUDE.md",
    "uv run --locked pytest --junitx=../CLAUDE.md",
    "uv run --locked pytest --cov-report=html",
    "uv run --locked pytest -o cache_dir=app",
    "uv run --locked pytest -p some_plugin",
    "uv run --locked mypy --html-report x app",
    "uv run pytest -q",
    "uv pip install x",
    "uv run --locked python -c 1",
    "python -c 'import os'",
    "sed -i 's/a/b/' x",
    "sed -n 's/a/b/w out' x",
    "sed -n '1p;e rm x' x",
    "find . -delete",
    "find . -exec rm '{}' +",
    "sort -o x y",
    "sort -uo x y",
    "sort y",
    "uniq a b",
    # .env reads (review round 1, F1).
    "cat .env",
    "cat .env*",
    "cat .e?v",
    "cat .{env,x}",
    "grep X backend/.env",
    "grep -f.env x",
    "grep -rn PASSWORD .",
    "grep -Rn PASSWORD .",
    "grep --recursive PASSWORD .",
    "grep -d recurse PASSWORD .",
    "grep -f .aws/credentials x",
    # Text the tokenizer must not misread (review round 2, F1 and F2).
    "true x#; cat .env",
    "true x#; rm -rf backend",
    'cat \\"x .e* y\\"',
    "echo \\' $DATABASE_URL \\'",
    "echo 'unclosed",
    'echo "$HOME"',
    'echo "`id`"',
    "echo a\\;b",
    'echo "a\\" "; cat .env #"',
    'echo "a\\" "; rm -rf backend #"',
    "git diff --no-index /dev/null x",
    "git diff --no-i /dev/null x",
    "uv run --locked pytest -q | ",
]


def run(payload: dict[str, object]) -> int:
    return subprocess.run(  # noqa: S603 (fixed argv: this interpreter and the hook path)
        [sys.executable, "-I", HOOK], input=json.dumps(payload), capture_output=True, text=True
    ).returncode


def main() -> None:
    wrong = []
    for command in ALLOW:
        if run({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "."}) != 0:
            wrong.append(f"should allow Bash: {command!r}")
    for command in BLOCK:
        if run({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "."}) != 2:
            wrong.append(f"should block Bash: {command!r}")

    with tempfile.TemporaryDirectory() as tmp:
        # A symlink with a harmless name that points at a .env file (no real secret).
        with open(os.path.join(tmp, ".env"), "w") as f:
            f.write("PLACEHOLDER=1\n")
        os.symlink(os.path.join(tmp, ".env"), os.path.join(tmp, "notes.txt"))
        tool_cases = [
            ("Read", {"file_path": "/repo/.env"}, 2),
            ("Read", {"file_path": "/repo/.env.local"}, 2),
            ("Read", {"file_path": os.path.join(tmp, "notes.txt")}, 2),
            ("Read", {"file_path": "/repo/.env.example"}, 0),
            ("Read", {"file_path": "/repo/CLAUDE.md"}, 0),
            ("Grep", {"pattern": "SECRET", "path": "/repo/.env"}, 2),
            ("Grep", {"pattern": "SECRET", "path": ".", "glob": ".env*"}, 2),
            ("Grep", {"pattern": "SECRET", "path": "backend", "glob": "*.py"}, 0),
            ("Bash", {"command": "cat notes.txt"}, 2),
            # Globs that ripgrep would let through to .env (review round 2, F3).
            ("Grep", {"pattern": "S", "path": ".", "glob": "*nv"}, 2),
            ("Grep", {"pattern": "S", "path": ".", "glob": ".e[n]v"}, 2),
            ("Grep", {"pattern": "S", "path": ".", "glob": "**/.env.*"}, 2),
            ("Grep", {"pattern": "S", "path": ".", "glob": "*.{py,env}"}, 2),
            ("Grep", {"pattern": "S", "path": ".", "glob": "!*.py"}, 2),
            ("Grep", {"pattern": "S", "path": ".", "glob": "*.{py,md}"}, 0),
            # Secrets outside the project, under the home directory (review round 2, F4).
            ("Read", {"file_path": os.path.expanduser("~/.ssh/id_rsa")}, 2),
            ("Read", {"file_path": os.path.expanduser("~/.config/gh/hosts.yml")}, 2),
            ("Bash", {"command": "cat " + os.path.expanduser("~/.ssh/id_rsa")}, 2),
            ("Grep", {"pattern": "S", "path": os.path.expanduser("~/.aws")}, 2),
            ("Read", {"file_path": "/usr/lib/python3/shlex.py"}, 0),
        ]
        for tool, tool_input, want in tool_cases:
            if run({"tool_name": tool, "tool_input": tool_input, "cwd": tmp}) != want:
                wrong.append(f"{tool} {tool_input} should exit {want}")

    total = len(ALLOW) + len(BLOCK) + len(tool_cases)
    print("\n".join(wrong))
    counts = f"{len(ALLOW)} allow, {len(BLOCK)} block, {len(tool_cases)} tool"
    print(f"{total} cases ({counts}); wrong: {len(wrong)}")
    sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
