import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logging import setup_logging, vercel_request_id
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security import SecurityHeadersMiddleware

setup_logging()

logger = logging.getLogger("api")

_IS_PRODUCTION = bool(os.environ.get("VERCEL") or os.environ.get("PRODUCTION"))

# Surface partially-configured environments (e.g. a Vercel preview deploy
# that's missing prod env vars) as a single startup WARNING instead of a
# Pydantic ValidationError that crashes the worker on import — which used
# to convert every favicon / root scrape on those URLs into a 500 with a
# full stack trace. Static routes (/health, /, /favicon.*) keep working;
# anything that hits the DB or auth bounces a clean 503 / 401 through the
# existing per-request handlers.
_runtime_errors = settings.runtime_ready_errors()
if _runtime_errors:
    logger.warning(
        "Backend booting in degraded mode; missing env vars: %s. "
        "Static endpoints will respond; authenticated API routes will 503 / 401.",
        ", ".join(_runtime_errors),
    )

app = FastAPI(
    title="Equip API",
    description=(
        "RESTful API for the Equip learning platform. "
        "Provides endpoints for course management, user enrollment, "
        "progress tracking, and file uploads."
    ),
    version="1.0.0",
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
)


app.add_middleware(SecurityHeadersMiddleware)

# GZip JSON responses larger than ~1KB. Starlette runs middleware in LIFO order
# on the response path, so this sits between SecurityHeaders (innermost, closest
# to the route) and CORS (outermost). That way Content-Length already reflects
# the compressed payload by the time CORS/logging sees it.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)

app.add_middleware(RateLimitMiddleware, calls=100, window=60)

# CORSMiddleware handles both the OPTIONS preflight and the ACAO headers on the
# actual response. We match against an explicit allow-list plus a regex that
# covers every Vercel alias for the frontend (production, branch, preview) and
# any localhost port, so dev servers and PR previews keep working without env
# changes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Request-Id"],
    max_age=3600,
)

app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    # Constraint violations (unique/foreign-key/check) mean the request
    # conflicts with current state — not that the database is down. We pull the
    # pgcode and constraint name off ``exc.orig`` so log search can jump
    # straight to the offending constraint instead of fishing through the full
    # rendered SQL statement.
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) if diag is not None else None
    logger.warning(
        "Integrity error on %s %s pgcode=%s constraint=%s: %s",
        request.method,
        request.url.path,
        pgcode,
        constraint,
        exc,
    )
    return JSONResponse(
        status_code=409,
        content={"detail": "Request conflicts with current state of the resource."},
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    # ``exc_info=True`` so the DatadogHTTPHandler ships the full stack
    # trace as ``error.stack``. Without it the log line only carries the
    # exception's ``str()`` -- useful for IntegrityError where we already
    # extracted pgcode + constraint, but useless for the general case
    # (lock timeout, connection drop mid-statement, OperationalError)
    # where the originating call site is what we actually need.
    logger.error(
        "Database error on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable. Please try again."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Per-request correlation id. In production Vercel attaches its own
    # unique id on the ``x-vercel-id`` header; we reuse it so a RUM
    # session error and the backend log line that produced it can be
    # joined by the same value already visible in the Vercel log viewer.
    # Outside Vercel (local dev, self-host) we mint a UUID so the field
    # is always populated and the contract is consistent everywhere.
    # Stashing it in a contextvar lets the DatadogHTTPHandler tag every
    # WARNING+ log emitted during this request with the same id.
    request_id = request.headers.get("x-vercel-id") or uuid.uuid4().hex
    token = vercel_request_id.set(request_id)
    try:
        start = time.time()
        response = await call_next(request)
        # Surface the id back to the caller (and to RUM) so a user
        # reporting a bug can quote it and we can pivot from a single
        # browser session straight to the backend log line. The header
        # is already listed in ``expose_headers`` on the CORS config.
        response.headers["X-Request-Id"] = request_id
        duration = round((time.time() - start) * 1000, 1)
        logger.info(
            "%s %s %s %sms",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response
    finally:
        vercel_request_id.reset(token)


_ROOT_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="shortcut icon" href="/favicon.ico">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#2F7A53">
<title>Equip API</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       max-width:520px;margin:6rem auto;padding:0 1.5rem;color:#1a1a2e;
       background:#FAF7F1;line-height:1.55}
  h1{font-size:1.5rem;margin:0 0 .25rem;color:#2F7A53}
  p{margin:.5rem 0;color:#4a4a6a;font-size:.95rem}
  code{background:#fff;padding:.1em .35em;border-radius:4px;font-size:.9em}
  a{color:#422277;text-decoration:none;border-bottom:1px solid #422277}
  @media (prefers-color-scheme:dark){body{background:#1a1a1d;color:#fbfaf7}
    h1{color:#A98FE3}p{color:#c5c2cf}code{background:#2a2a2e}
    a{color:#A98FE3;border-bottom-color:#A98FE3}}
</style>
</head>
<body>
<h1>Equip API</h1>
<p>v1.0.0 — RESTful backend for the Equip learning platform.</p>
<p>This is a JSON API; routes live under <code>/api/v1/*</code>.
Try <code>/health</code> for a quick liveness probe.</p>
<p>Frontend: <a href="https://equipbible.com">equipbible.com</a></p>
</body>
</html>
"""


@app.get("/")
async def root(request: Request) -> Response:
    """Serve a small HTML landing for browsers (so the tab favicon and
    Vercel's project-card scraper both pick up our brand mark) and JSON
    for API clients. Negotiation is based on the request's Accept header:
    anything that lists ``text/html`` ahead of (or without) ``application/json``
    gets HTML; everything else keeps the historical JSON contract."""
    accept = request.headers.get("accept", "").lower()
    wants_html = "text/html" in accept and (
        "application/json" not in accept or accept.find("text/html") < accept.find("application/json")
    )
    if wants_html:
        return HTMLResponse(_ROOT_HTML)
    return JSONResponse({"message": "Equip API", "version": "1.0.0"})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


_STATIC_DIR = Path(__file__).parent / "static"

# Sage-on-cream Equip API icon set. Same "E" glyph as the frontend
# favicon (warm-paper inverse) but on a deep-sage ``--success`` field
# (#2F7A53) instead of the violet ``--primary``, so the
# api.equipbible.com browser tab and Vercel project tile are visually
# distinct from equipbible.com while staying inside the brand palette.
#
# Why multiple formats:
# - .svg scales perfectly but some legacy scrapers + iOS apple-touch-icon
#   rendering favor PNG/ICO binaries.
# - Multi-resolution .ico (16/32/48) is what most browsers cache first
#   from the /favicon.ico path; serving a real ICO container avoids the
#   "SVG-masquerading-as-ICO" silent-fallback some clients hit.
# - apple-touch-icon.png 180x180 = iOS Home Screen.
# - android-chrome-{192,512}.png = Android PWA install + adaptive icon.
#
# Regenerate via ``python app/static/_generate_icons.py`` whenever the
# canonical SVG shape changes.
_ICON_FILES: dict[str, tuple[str, str]] = {
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
    "/favicon-16x16.png": ("favicon-16x16.png", "image/png"),
    "/favicon-32x32.png": ("favicon-32x32.png", "image/png"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "/apple-touch-icon-precomposed.png": ("apple-touch-icon.png", "image/png"),
    "/android-chrome-192x192.png": ("android-chrome-192x192.png", "image/png"),
    "/android-chrome-512x512.png": ("android-chrome-512x512.png", "image/png"),
}


def _icon_route(filename: str, media_type: str):
    """Build a handler that returns the icon file with strong-ish caching.
    24-hour public cache: long enough that browsers don't re-fetch on every
    tab open, short enough that a real change rolls out within a day even
    if a downstream proxy ignores ETags."""

    async def handler() -> FileResponse:
        return FileResponse(
            _STATIC_DIR / filename,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=86400, must-revalidate"},
        )

    return handler


for _path, (_file, _mime) in _ICON_FILES.items():
    app.add_api_route(
        _path,
        _icon_route(_file, _mime),
        include_in_schema=False,
        methods=["GET", "HEAD"],
    )


# /vite.svg is a noise endpoint that some clients probe; 204 keeps the
# logs clean without raising 404 alerts.
@app.get("/vite.svg", include_in_schema=False)
@app.head("/vite.svg", include_in_schema=False)
async def _noise_icons() -> Response:
    return Response(status_code=204)
