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


def test_api_v1_health_alias_returns_ok():
    """External monitors (Datadog synthetics) defaulted to the
    API-namespaced ``/api/v1/health`` and hit 404s, padding the
    error-rate panel. The alias body must match ``/health`` so a
    synthetic switching between the two URLs reads identically."""
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/health")
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


def test_the_api_host_tells_crawlers_to_stay_out():
    """robots.txt is per-host, and this host is not the public site.

    The frontend's robots.txt has a comment saying "do not crawl the API"
    — a thing it cannot actually say, because it is served from
    equipbible.com and governs only equipbible.com. A crawler arriving at
    api.equipbible.com asked for this file on 2026-09-21 and got a 404,
    which means "no rules, crawl what you like".
    """
    with TestClient(app) as tc:
        resp = tc.get("/robots.txt")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "User-agent: *" in body
    assert "Disallow: /" in body
    # It must not accidentally allow anything: a stray Allow line is how a
    # blanket Disallow stops meaning what it says.
    assert "Allow:" not in body


def test_robots_is_cacheable_and_answers_head():
    """A crawler re-reads robots.txt before each crawl, and some issue a
    HEAD first. Neither should reach the router as a 404."""
    with TestClient(app) as tc:
        get = tc.get("/robots.txt")
        head = tc.head("/robots.txt")
    assert head.status_code == 200
    assert "max-age=86400" in get.headers["cache-control"]
