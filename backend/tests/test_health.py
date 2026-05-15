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


def test_response_includes_x_request_id_header():
    """Every response must carry an ``X-Request-Id`` header so a user
    reporting a bug can quote it and we can pivot from a single browser
    session straight to the backend log line. Outside Vercel (here in
    the test client) the middleware mints a UUID hex so the field is
    always populated."""
    with TestClient(app) as tc:
        resp = tc.get("/health")
    assert resp.status_code == 200
    request_id = resp.headers.get("X-Request-Id")
    assert request_id, "X-Request-Id must be set on every response"
    # UUID hex (32 hex chars) when generated locally; Vercel ids look
    # like ``iad1::abc123`` so we only sanity-check non-emptiness here.
    assert len(request_id) >= 16


def test_response_echoes_vercel_request_id_when_present():
    """When Vercel forwards ``x-vercel-id`` we surface it verbatim
    instead of minting our own, so the value matches what the Vercel
    log viewer already shows for the same request."""
    with TestClient(app) as tc:
        resp = tc.get("/health", headers={"x-vercel-id": "iad1::test-abc-123"})
    assert resp.headers.get("X-Request-Id") == "iad1::test-abc-123"
