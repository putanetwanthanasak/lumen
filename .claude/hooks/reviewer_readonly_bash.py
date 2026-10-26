r"""PreToolUse hook for the independent-reviewer subagent: read-only tools only.

Subagent frontmatter cannot limit Bash to specific commands, so this hook does
it. It reads the hook JSON on stdin and exits 0 to allow the call or 2 to block
it. On a block, the reason goes back to the subagent on stderr.

Bash rules (an allowlist; anything not listed is blocked):
- The command is parsed by tokenize(), which accepts only a subset of shell
  syntax whose meaning is exact. Unquoted words use only the characters in
  SAFE_UNQUOTED. Single quotes are literal. Double quotes may not contain $, `,
  \ or !. Parts may be chained with |, && or ||, and "2>&1" may follow a word.
  Every other character is blocked, so there is no redirection, ';', '#',
  subshell, background job, expansion, glob, brace or tilde. Nothing in the
  command can be hidden from the checks below.
- git: read-only subcommands only. No -c config overrides, and no output file
  or external diff tool, including abbreviated long options.
- pytest, mypy and ruff run only as "uv run --locked|--frozen <tool>", so uv
  never rewrites uv.lock. Each tool takes only the options listed below, so no
  report, cache or temp-dir option can write or delete files. ruff check runs
  without fixes; ruff format runs only with --check or --diff.
- grep: no recursive search. Use the Grep tool, which skips gitignored files.
- sed: only "sed -n" with a print-only script. sort and uniq: stdin only.

Read, Grep and Bash rules:
- No .env file (except .env.example) may be read or searched, because secret
  values must never be printed (CLAUDE.md Hard rule 2). Paths are resolved, so
  a symlink to .env is caught too. A Grep glob is blocked if it could match a
  .env name, because ripgrep lets a glob override .gitignore.
- Nothing under the home directory outside this project may be read or
  searched (for example ~/.ssh, ~/.aws or the gh token).
"""

import fnmatch
import json
import os
import re
import string
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
GIT_BRANCH_LIST_ARGS = {"branch", "--show-current", "--list", "-a", "-r", "-v", "-vv"}
FORBIDDEN_GIT_GLOBAL_ARGS = ("-c", "--config-env", "--exec-path")
# git accepts any unambiguous prefix of a long option, so prefixes are matched too.
FORBIDDEN_GIT_LONG_OPTIONS = ("--output", "--ext-diff", "--no-index")
PLAIN_READERS = {"cat", "head", "tail", "wc", "ls", "cut", "pwd", "echo", "cd", "true"}
FORBIDDEN_FIND_PREFIXES = ("-delete", "-exec", "-ok", "-fprint", "-fls")
SED_PRINT_SCRIPT = re.compile(r"(\d+|\$|/[^/]*/)(,(\d+|\$|/[^/]*/))?p")

PYTEST_FLAGS = {
    "-q",
    "-v",
    "-vv",
    "-x",
    "-s",
    "-l",
    "--lf",
    "--ff",
    "--co",
    "--collect-only",
    "--no-cov",
    "--cov=app",
    "--cov-branch",
    "--cov-report=term",
    "--cov-report=term-missing",
    "--hypothesis-show-statistics",
}
PYTEST_FLAG_PATTERN = re.compile(
    r"--tb=(auto|long|short|line|native|no)|-r[a-zA-Z]+|--durations=\d+|--maxfail=\d+"
)
PYTEST_VALUE_OPTIONS = {"-k", "-m"}
MYPY_FLAGS = {"--pretty", "--show-error-codes", "--no-error-summary", "--show-column-numbers"}
RUFF_CHECK_FLAGS = {"--statistics", "--diff", "--no-cache", "--output-format=concise"}
RUFF_FORMAT_FLAGS = {"--check", "--diff", "--no-cache"}
RUFF_VALUE_OPTIONS = {"--select"}
SORT_FLAGS = re.compile(r"-[nruh]+")
UNIQ_FLAGS = {"-c", "-d", "-u"}

CHAIN_OPERATORS = {"|", "&&", "||"}
SAFE_UNQUOTED = set(string.ascii_letters + string.digits + "_-./:=,@+%")
NOT_IN_DOUBLE_QUOTES = set("$`\\!\n")
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
HOME_DIR = os.path.realpath(os.path.expanduser("~"))
# Names a Grep glob must not be able to match.
ENV_SAMPLES = (".env", ".env.local", ".env.production", "x/.env", "x/.env.local")
# ".env" anywhere in a token (also inside "-f.env" or "--exclude=.env"), except ".env.example".
ENV_TOKEN = re.compile(r"\.env(?!\.example\b|[A-Za-z0-9_])")


def deny(reason: str) -> None:
    print(f"Blocked by the independent-reviewer read-only hook: {reason}", file=sys.stderr)
    sys.exit(2)


def touches_env(value: str, cwd: str) -> bool:
    """True if value names a .env file, directly or through a symlink."""
    if ENV_TOKEN.search(value):
        return True
    if not value or value.startswith("-"):
        return False
    resolved = os.path.realpath(os.path.join(cwd, value))
    return bool(ENV_TOKEN.search(os.path.basename(resolved)))


def outside_project_in_home(value: str, cwd: str) -> bool:
    """True if value resolves to a path under the home directory but outside this project."""
    if not value or value.startswith("-"):
        return False
    resolved = os.path.realpath(os.path.join(cwd, value))
    in_home = os.path.commonpath([resolved, HOME_DIR]) == HOME_DIR
    in_project = os.path.commonpath([resolved, PROJECT_DIR]) == PROJECT_DIR
    return in_home and not in_project


def expand_braces(glob: str) -> list[str]:
    """Expand the first {a,b} group, recursively, as ripgrep does."""
    match = re.search(r"\{([^{}]*)\}", glob)
    if not match:
        return [glob]
    head, tail = glob[: match.start()], glob[match.end() :]
    return [g for alt in match.group(1).split(",") for g in expand_braces(head + alt + tail)]


def glob_may_match_env(glob: str) -> bool:
    if glob.startswith("!") or touches_env(glob, "/"):
        return True
    return any(fnmatch.fnmatchcase(name, g) for g in expand_braces(glob) for name in ENV_SAMPLES)


def check_options(
    args: list[str],
    flags: set[str],
    value_options: set[str] | None = None,
    pattern: re.Pattern[str] | None = None,
) -> str | None:
    """Allow positional arguments and the listed options only."""
    value_options = value_options or set()
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
        elif not arg.startswith("-") or arg in flags:
            continue
        elif arg in value_options:
            skip_next = True
        elif arg.split("=", 1)[0] in value_options:
            continue
        elif not (pattern and pattern.fullmatch(arg)):
            return f"option '{arg}' is not on the read-only allowlist"
    return None


def check_tool(cmd: str, args: list[str]) -> str | None:
    """pytest, mypy and ruff, with only options that cannot write or delete files."""
    if cmd == "pytest":
        return check_options(args, PYTEST_FLAGS, PYTEST_VALUE_OPTIONS, PYTEST_FLAG_PATTERN)
    if cmd == "mypy":
        return check_options(args, MYPY_FLAGS)
    if args[:1] == ["check"]:
        return check_options(args[1:], RUFF_CHECK_FLAGS, RUFF_VALUE_OPTIONS)
    if args[:1] == ["format"] and ("--check" in args or "--diff" in args):
        return check_options(args[1:], RUFF_FORMAT_FLAGS)
    return "ruff is allowed only as 'ruff check' or 'ruff format --check'"


def check_git(args: list[str]) -> str | None:
    sub_at = next((i for i, a in enumerate(args) if not a.startswith("-")), len(args))
    sub = args[sub_at] if sub_at < len(args) else None
    if sub not in READ_ONLY_GIT:
        return f"'git {sub}' is not a read-only git command"
    if any(a.split("=", 1)[0] in FORBIDDEN_GIT_GLOBAL_ARGS for a in args[:sub_at]):
        return "git config overrides are not allowed"
    for arg in args:
        name = arg.split("=", 1)[0]
        if len(name) >= 4 and any(o.startswith(name) for o in FORBIDDEN_GIT_LONG_OPTIONS):
            return "git output files and external diff tools are not allowed"
    if sub == "branch" and not set(args) <= GIT_BRANCH_LIST_ARGS:
        return "git branch is allowed only to list branches"
    return None


def is_recursive_grep(args: list[str]) -> bool:
    for arg in args:
        if arg.startswith(("--recursive", "--dereference-recursive", "--directories", "-d")):
            return True
        if arg.startswith("-") and not arg.startswith("--") and ("r" in arg or "R" in arg):
            return True
    return False


def check_part(tokens: list[str], cwd: str) -> str | None:
    """Return why this command part is blocked, or None if it is read-only."""
    if not tokens:
        return "empty command part"
    if any(touches_env(t, cwd) for t in tokens):
        return "reading a .env file is not allowed (secret values must never be printed)"
    if any(outside_project_in_home(t, cwd) for t in tokens):
        return "reading files in the home directory outside this project is not allowed"
    cmd, args = tokens[0], tokens[1:]

    if cmd == "uv":
        uv_run = args[:1] == ["run"] and args[1:2] in (["--locked"], ["--frozen"])
        if uv_run and args[2:3] in (["pytest"], ["mypy"], ["ruff"]):
            return check_tool(args[2], args[3:])
        return "uv is allowed only as 'uv run --locked pytest|mypy|ruff ...'"
    if cmd in ("pytest", "mypy", "ruff"):
        return check_tool(cmd, args)
    if cmd == "git":
        return check_git(args)
    if cmd == "grep":
        if is_recursive_grep(args):
            return "recursive grep is not allowed; use the Grep tool (it skips gitignored files)"
        if any(a.startswith("--file") or re.fullmatch(r"-[a-zA-Z]*f.*", a) for a in args):
            return "grep -f (patterns from a file) is not allowed"
        return None
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
    if cmd == "sort":
        if all(SORT_FLAGS.fullmatch(a) for a in args):
            return None
        return "sort is allowed only on stdin, with -n, -r, -u or -h"
    if cmd == "uniq":
        if set(args) <= UNIQ_FLAGS:
            return None
        return "uniq is allowed only on stdin, with -c, -d or -u"
    if cmd in PLAIN_READERS:
        return None
    return f"'{cmd}' is not on the read-only allowlist"


def tokenize(command: str) -> list[str] | str:
    """Split a command into words and chain operators, or return why it is blocked.

    Only the subset described in the module docstring is accepted, so every
    word here is exactly the word bash would pass to the program.
    """
    tokens: list[str] = []
    word: str | None = None
    i = 0
    while i < len(command):
        c = command[i]
        if c in " \t":
            if word is not None:
                tokens.append(word)
                word = None
            i += 1
        elif word is None and re.match(r"2>&1(?=[ \t|]|$)", command[i:]):
            i += 4
        elif command.startswith(("&&", "||"), i) or c == "|":
            if word is not None:
                tokens.append(word)
                word = None
            op = "|" if c == "|" and not command.startswith("||", i) else command[i : i + 2]
            tokens.append(op)
            i += len(op)
        elif c == "'":
            end = command.find("'", i + 1)
            if end < 0:
                return "unclosed single quote"
            word = (word or "") + command[i + 1 : end]
            i = end + 1
        elif c == '"':
            end = command.find('"', i + 1)
            if end < 0:
                return "unclosed double quote"
            quoted = command[i + 1 : end]
            if NOT_IN_DOUBLE_QUOTES & set(quoted):
                return (
                    "$, `, \\, ! and newlines are not allowed in double quotes; use single quotes"
                )
            word = (word or "") + quoted
            i = end + 1
        elif c in SAFE_UNQUOTED:
            word = (word or "") + c
            i += 1
        else:
            return (
                f"{c!r} is not allowed outside quotes (no redirection, ';', '#', '&', "
                "subshell, expansion, glob or escape); quote patterns with single quotes"
            )
    if word is not None:
        tokens.append(word)
    return tokens


def check_bash(command: str, cwd: str) -> str | None:
    tokens = tokenize(command)
    if isinstance(tokens, str):
        return tokens
    part: list[str] = []
    for token in [*tokens, "&&"]:
        if token not in CHAIN_OPERATORS:
            part.append(token)
            continue
        reason = check_part(part, cwd)
        if reason:
            return reason
        if part[:1] == ["cd"] and len(part) > 1:
            cwd = os.path.join(cwd, part[1])
        part = []
    return None


def main() -> None:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    cwd = str(payload.get("cwd") or os.getcwd())
    reason = None
    if tool == "Bash":
        reason = check_bash(str(tool_input.get("command", "")), cwd)
    elif tool in ("Read", "Grep"):
        path = str(tool_input.get("file_path" if tool == "Read" else "path") or "")
        glob = str(tool_input.get("glob") or "")
        if touches_env(path, cwd) or (glob and glob_may_match_env(glob)):
            reason = "reading or searching a .env file is not allowed"
        elif outside_project_in_home(path, cwd):
            reason = "reading files in the home directory outside this project is not allowed"
    if reason:
        deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
