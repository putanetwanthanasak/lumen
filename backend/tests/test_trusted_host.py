"""S8: loopback binding alone does not stop DNS rebinding. A page on evil.example can
make its name resolve to 127.0.0.1 and then call the API from the user's browser
with `Host: evil.example`. Only loopback host names are served."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "127.0.0.1", "testserver"])
def test_S8_loopback_hosts_served(host: str) -> None:
    assert client.get("/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:8000", "192.168.1.20:8000", "127.0.0.1.evil.example"]
)
def test_S8_other_hosts_rejected_before_any_route(host: str) -> None:
    for method, path in [("GET", "/debts/summary"), ("POST", "/webhooks/bnpl")]:
        response = client.request(method, path, headers={"Host": host, "X-Demo-User": "user_a"})
        assert response.status_code == 400
        assert response.text == "Invalid host header"
