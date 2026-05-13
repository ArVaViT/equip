import logging
import os
import time
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
    logger.error("Database error on %s %s: %s", request.method, request.url.path, exc)
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
    # Vercel attaches a unique id to every inbound request on the
    # ``x-vercel-id`` header. Stashing it in a contextvar lets the
    # DatadogHTTPHandler tag every WARNING+ log emitted during this
    # request with the same id, so a RUM session error and the backend
    # log line that produced it can be correlated by Vercel request id.
    token = vercel_request_id.set(request.headers.get("x-vercel-id"))
    try:
        start = time.time()
        response = await call_next(request)
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
<link rel="apple-touch-icon" href="/favicon.svg">
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
_FAVICON_SVG = _STATIC_DIR / "favicon.svg"


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
async def favicon() -> FileResponse:
    """Serve the sage-on-cream Equip API mark. Same glyph as the frontend
    favicon (warm-paper E) but on the ``--success`` deep-sage background
    (``#2F7A53``) instead of the ``--primary`` violet, so the
    api.equipbible.com browser tab is visually distinct from
    equipbible.com at a glance while staying inside the brand palette.
    Both ``/favicon.ico`` and ``/favicon.svg`` resolve here; browsers and
    Vercel's project-card scraper accept SVG behind either path."""
    return FileResponse(_FAVICON_SVG, media_type="image/svg+xml")


# /favicon.png and /vite.svg are noise endpoints that some clients
# probe but which we don't actually want to serve. 204 keeps the
# logs clean without raising 404 alerts.
@app.get("/favicon.png", include_in_schema=False)
@app.get("/vite.svg", include_in_schema=False)
async def _noise_icons() -> Response:
    return Response(status_code=204)
