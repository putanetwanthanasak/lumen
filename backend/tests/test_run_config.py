"""S9: the server that runs the demo is pinned, and the documented command keeps it
on loopback (L60 1: no end-user auth, so it must never listen on the network)."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_S9_uvicorn_pinned_exactly_in_pyproject_and_lock() -> None:
    project = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text())
    pins = [d for d in project["project"]["dependencies"] if d.startswith("uvicorn")]
    assert len(pins) == 1
    assert re.fullmatch(r"uvicorn==\d+\.\d+\.\d+", pins[0]), pins
    lock = tomllib.loads((ROOT / "backend" / "uv.lock").read_text())
    [locked] = [p for p in lock["package"] if p["name"] == "uvicorn"]
    assert locked["version"] == pins[0].removeprefix("uvicorn==")


def test_S9_readme_runs_uvicorn_on_loopback_without_reload() -> None:
    readme = (ROOT / "README.md").read_text()
    commands = [line for line in readme.splitlines() if "uvicorn app.main:app" in line]
    assert commands, "README must show the uvicorn command"
    for command in commands:
        assert "--host 127.0.0.1" in command
        assert "--reload" not in command
