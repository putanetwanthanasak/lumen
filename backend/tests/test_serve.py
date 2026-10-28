"""KD-01: the one-server demo (app.serve): the built screens at /, the unchanged API
at /api, loopback hosts only, and nothing outside the build is ever served."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.serve import FRONTEND_DIST, create_serving_app

INDEX = "<!doctype html><title>KidNee</title>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    build = tmp_path / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text(INDEX)
    (build / "assets" / "app.js").write_text("export {}")
    (tmp_path / "secret.txt").write_text("outside the build")
    return build


def client(dist: Path | None) -> TestClient:
    return TestClient(create_serving_app(create_app(Settings()), dist))


def test_KD_01_root_serves_the_build_and_api_is_under_api(dist: Path) -> None:
    c = client(dist)
    page = c.get("/")
    assert (page.status_code, page.text) == (200, INDEX)
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/api/health").json() == {"status": "ok"}
    # The prefix is stripped like the Vite proxy does: the API's own routes, auth included.
    assert c.get("/api/debts/summary").status_code == 401


def test_KD_01_api_routes_are_not_served_at_the_root(dist: Path) -> None:
    assert client(dist).get("/health").status_code == 404


def test_KD_01_without_a_build_only_the_api_is_served(tmp_path: Path) -> None:
    for build in [None, tmp_path / "missing", tmp_path]:  # tmp_path has no index.html
        c = client(build)
        assert c.get("/").status_code == 404
        assert c.get("/api/health").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/../secret.txt",
        "/%2e%2e/secret.txt",
        "/assets/..%2f..%2fsecret.txt",
        "/%2e%2e%2fsecret.txt",
    ],
)
def test_KD_01_nothing_outside_the_build_is_served(dist: Path, path: str) -> None:
    response = client(dist).get(path)
    assert response.status_code == 404
    assert "outside the build" not in response.text


def test_KD_01_a_symlink_out_of_the_build_is_not_followed(dist: Path) -> None:
    (dist / "leak.txt").symlink_to(dist.parent / "secret.txt")
    response = client(dist).get("/leak.txt")
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/", "/api/health"])
def test_KD_01_untrusted_host_is_rejected_before_any_route(dist: Path, path: str) -> None:
    response = client(dist).get(path, headers={"Host": "evil.example"})
    assert response.status_code == 400


def test_KD_01_the_default_build_is_frontend_dist() -> None:
    assert FRONTEND_DIST.parts[-2:] == ("frontend", "dist")
    assert FRONTEND_DIST.parent.joinpath("package.json").is_file()
