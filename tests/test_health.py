from __future__ import annotations

from tests.conftest import make_client


def test_health_endpoint() -> None:
    client = make_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

