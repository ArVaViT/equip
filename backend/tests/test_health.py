from fastapi.testclient import TestClient

from app.main import app


def test_root_returns_api_info():
    with TestClient(app) as tc:
        resp = tc.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Equip API"
    assert "version" in body


def test_root_serves_html_for_browser_accept():
    """Browsers and the Vercel project-card scraper request the root
    with ``Accept: text/html``; we negotiate and serve a small HTML
    landing whose <link rel=icon> exposes our sage API favicon."""
    with TestClient(app) as tc:
        resp = tc.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "<title>Equip API</title>" in body
    assert '<link rel="icon" type="image/svg+xml" href="/favicon.svg">' in body
    assert "#2F7A53" in body  # theme-color = our --success sage


def test_health_returns_ok():
    with TestClient(app) as tc:
        resp = tc.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
