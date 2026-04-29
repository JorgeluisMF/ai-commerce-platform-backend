from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert "services" in body
    assert body["services"]["db"] in ("ok", "error")
    assert body["services"]["redis"] in ("ok", "error")


def test_health_includes_request_id_header() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
