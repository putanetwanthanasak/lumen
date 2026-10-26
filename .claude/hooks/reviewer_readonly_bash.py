"""PreToolUse hook for the independent-reviewer subagent: read-only tools only.

Subagent frontmatter cannot limit Bash to specific commands, so this hook does
it. It reads the hook JSON on stdin and exits 0 to allow the call or 2 to block
it. On a block, the reason goes back to the subagent on stderr.

Bash rules:
- No redirection, command substitution, ';', background jobs or variable
  expansion. The one exception is "2>&1", which writes no file.
- Parts may be chained with |, && or ||, and every part is checked.
- git: read-only subcommands only, with no -c, pager, or output-file options.
- ruff: "check" without --fix; "format" only with --check or --diff.
- pytest, mypy, and "uv run" with one of these, are allowed. The test DB is
  disposable.
- sed: only "sed -n" with a print-only script.

Read, Grep and Bash rules:
- No .env file (except .env.example) may be read or searched, because secret values must
  never be printed (CLAUDE.md Hard rule 2).
"""

import json
import os
import re
import shlex
import sys

READ_ONLY_GIT = {
    "diff",
    "log",
    "show",
    "status",
    "blame",
    "ls-files",
    "rev-parse",
    "merge-base",
    "branch",
}
FORBIDDEN_GIT_GLOBAL_ARGS = ("-c", "--config-env", "--exec-path")
FORBIDDEN_GIT_ARGS = ("--output", "--ext-diff")
PLAIN_READERS = {
    "cat",
    "head",
    "tail",
    "wc",
    "ls",
    "grep",
    "sort",
    "uniq",
    "cut",
    "nl",
    "stat",
    "pwd",
    "echo",
    "cd",
}
FORBIDDEN_FIND_PREFIXES = ("-delete", "-exec", "-ok", "-fprint", "-fls")
SED_PRINT_SCRIPT = re.compile(r"(\d+|\$|/[^/]*/)(,(\d+|\$|/[^/]*/))?p")
CHAIN_OPERATORS = {"|", "&&", "||"}
ENV_FILE = re.compile(r"(^|/)\.env($|\.(?!example$))")


def deny(reason: str) -> None:
    print(f"Blocked by the independent-reviewer read-only hook: {reason}", file=sys.stderr)
    sys.exit(2)


def check_part(tokens: list[str]) -> str | None:
    """Return why this command part is blocked, or None if it is read-only."""
    if not tokens:
        return "empty command part"
    if any(ENV_FILE.search(t) for t in tokens):
        return "reading a .env file is not allowed (secret values must never be printed)"
    cmd, args = tokens[0], tokens[1:]

    if cmd == "uv":
        rest = (
            [a for a in args[1:] if a not in ("--frozen", "--no-sync")]
            if args[:1] == ["run"]
            else []
        )
        if rest and rest[0] in ("pytest", "mypy", "ruff"):
            return check_part(rest)
        return "uv is allowed only as 'uv run pytest|mypy|ruff ...'"
    if cmd == "git":
        sub_at = next((i for i, a in enumerate(args) if not a.startswith("-")), len(args))
        sub = args[sub_at] if sub_at < len(args) else None
        if sub not in READ_ONLY_GIT:
            return f"'git {sub}' is not a read-only git command"
        if any(
            a == f or a.startswith(f + "=")
            for a in args[:sub_at]
            for f in FORBIDDEN_GIT_GLOBAL_ARGS
        ):
            return "git config overrides are not allowed"
        if any(a == f or a.startswith(f + "=") for a in args for f in FORBIDDEN_GIT_ARGS):
            return "git output files and external diff tools are not allowed"
        if sub == "branch" and not set(args) <= {
            "branch",
            "--show-current",
            "--list",
            "-a",
            "-r",
            "-v",
            "-vv",
        }:
            return "git branch is allowed only to list branches"
        return None
    if cmd in ("pytest", "mypy"):
        return None
    if cmd == "ruff":
        if args[:1] == ["check"] and not any(
            a.startswith(("--fix", "--unsafe-fixes", "--add-noqa")) for a in args
        ):
            return None
        if args[:1] == ["format"] and ("--check" in args or "--diff" in args):
            return None
        return "ruff is allowed only as 'ruff check' without --fix, or 'ruff format --check'"
    if cmd == "sed":
        options = {a for a in args if a.startswith("-")}
        scripts = [a for a in args if not a.startswith("-")][:1]
        if options == {"-n"} and scripts and SED_PRINT_SCRIPT.fullmatch(scripts[0]):
            return None
        return "sed is allowed only as \"sed -n 'START,ENDp' FILE\""
    if cmd == "find":
        if any(a.startswith(FORBIDDEN_FIND_PREFIXES) for a in args):
            return "find with -delete, -exec, -ok or a file-writing action is not allowed"
        return None
    if cmd == "sort" and any(a.startswith(("-o", "--output")) for a in args):
        return "sort -o writes a file"
    if cmd in PLAIN_READERS:
        return None
    return f"'{cmd}' is not on the read-only allowlist"


def check_bash(command: str) -> str | None:
    if not command.strip():
        return "no command"
    scrubbed = command.replace("2>&1", " ")
    if "\n" in scrubbed.strip():
        return "multi-line commands are not allowed"
    if "`" in scrubbed or "$" in re.sub(r"'[^']*'", "", scrubbed):
        return "command substitution and variable expansion are not allowed"
    lexer = shlex.shlex(scrubbed, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as exc:
        return f"cannot parse the command: {exc}"
    part: list[str] = []
    for token in [*tokens, "&&"]:
        if token in CHAIN_OPERATORS:
            reason = check_part(part)
            if reason:
                return reason
            part = []
        elif token and set(token) <= set("();<>|&"):
            return f"'{token}' (redirection, ';', subshell or background job) is not allowed"
        else:
            part.append(token)
    return None


def main() -> None:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    if tool == "Bash":
        reason = check_bash(str(tool_input.get("command", "")))
    elif tool == "Grep" and ENV_FILE.search(os.path.normpath(str(tool_input.get("path", "")))):
        reason = "searching a .env file is not allowed"
    elif tool == "Read":
        path = str(tool_input.get("file_path", ""))
        reason = (
            "reading a .env file is not allowed"
            if ENV_FILE.search(os.path.normpath(path))
            else None
        )
    else:
        reason = None
    if reason:
        deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
