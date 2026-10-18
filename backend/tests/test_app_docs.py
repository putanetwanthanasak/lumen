"""S12: the API map (/docs, /redoc, /openapi.json) is served only when DEBUG is on."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.mark.parametrize("path", DOC_PATHS)
def test_S12_api_docs_off_by_default(path: str) -> None:
    client = TestClient(create_app(Settings(debug=False)))
    assert client.get(path).status_code == 404
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", DOC_PATHS)
def test_S12_api_docs_on_when_debug(path: str) -> None:
    client = TestClient(create_app(Settings(debug=True)))
    assert client.get(path).status_code == 200
