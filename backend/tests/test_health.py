from fastapi.testclient import TestClient

from app.main import app


def test_root_returns_api_info():
    with TestClient(app) as tc:
        resp = tc.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Equip API"
    assert "version" in body


def test_health_returns_ok():
    with TestClient(app) as tc:
        resp = tc.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
