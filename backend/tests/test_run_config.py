"""S9: the server that runs the demo is pinned, and the documented command and the
demo script keep it on loopback (L60 1: no end-user auth, so it must never listen on
the network)."""

import re
import tomllib
from pathlib import Path

import pytest
from pydantic import SecretStr

from demo.kidnee import HOST, KIDNEE_DB_NAME, KidneeConfig, create_if_missing, main
from demo.script import DemoConfig, reset_database

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


def test_L60_1_demo_binds_uvicorn_to_loopback_only() -> None:
    source = (ROOT / "backend" / "demo" / "script.py").read_text()
    hosts = re.findall(r'host="([^"]+)"', source)
    assert hosts == ["127.0.0.1"]
    assert "0.0.0.0" not in source  # noqa: S104


def test_demo_refuses_to_reset_any_other_database() -> None:
    for name in ["lumen", "lumen_test", "lumen_demo_x", 'lumen_demo"; DROP']:
        config = DemoConfig("postgresql://x/y", "postgresql://x/y", SecretStr("s"), db_name=name)
        with pytest.raises(SystemExit, match="Refusing to reset"):
            reset_database(config)


def test_KD_02_kidnee_demo_binds_uvicorn_to_loopback_only() -> None:
    source = (ROOT / "backend" / "demo" / "kidnee.py").read_text()
    hosts = re.findall(r'host="([^"]+)"', source)
    assert hosts == ["127.0.0.1"]
    assert HOST == "127.0.0.1"
    assert "0.0.0.0" not in source  # noqa: S104
    assert "0.0.0.0" not in (ROOT / "backend" / "app" / "serve.py").read_text()  # noqa: S104


def test_KD_02_readme_documents_the_kidnee_commands() -> None:
    readme = (ROOT / "README.md").read_text()
    for command in ["python -m demo.kidnee reset --yes", "python -m demo.kidnee serve"]:
        assert command in readme


@pytest.mark.parametrize(
    "name",
    ["lumen", "lumen_test", "lumen_demo", "lumen_kidnee_x", 'lumen_kidnee"; DROP', "LUMEN_KIDNEE"],
)
def test_KD_03_kidnee_refuses_any_other_database(name: str) -> None:
    config = KidneeConfig("postgresql://x/y", "postgresql://x/y", db_name=name)
    with pytest.raises(SystemExit, match="Refusing"):
        reset_database(config, KIDNEE_DB_NAME)
    with pytest.raises(SystemExit, match="Refusing"):
        create_if_missing(config)


def test_KD_03_kidnee_whitelist_is_the_demo_and_its_test_database_only() -> None:
    assert [n for n in ["lumen_kidnee", "lumen_kidnee_test"] if KIDNEE_DB_NAME.fullmatch(n)] == [
        "lumen_kidnee",
        "lumen_kidnee_test",
    ]


def test_KD_03_reset_needs_yes_before_touching_anything() -> None:
    with pytest.raises(SystemExit, match="--yes"):
        main(["reset"])
