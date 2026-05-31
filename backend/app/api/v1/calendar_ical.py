"""iCal subscription endpoints.

Two routes:

* ``POST /calendar/ical/token`` (auth) — issues a long-lived
  HMAC-signed token bound to the calling user, and returns the
  subscribe URL. Rotation is implicit: a fresh call updates ``iat``,
  invalidating any earlier token in case the user accidentally shared
  the link.
* ``GET /calendar/ical/feed`` (no session auth) — validates the
  token and returns RFC 5545 text/calendar. Designed so a calendar
  client can subscribe without sending a Bearer header.

Auth model: standalone signed token, not Supabase JWTs. We don't
want to expose a fully-privileged JWT in a calendar subscription URL
because calendar clients sometimes log the URL plain. The iCal token
carries only ``{sub, scope=ical}``; the route refuses tokens with
any other scope.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.orm import Session  # noqa: TC002 — FastAPI Depends runtime use

from app.api.dependencies import get_current_user
from app.api.v1.calendar import get_calendar_events
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.user import User
from app.services.calendar_ical import render_calendar

if TYPE_CHECKING:
    from app.schemas.calendar import CalendarEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar/ical", tags=["calendar"])

_TOKEN_SCOPE = "ical"
# 365 days. iCal subscriptions are passive: the client polls the URL
# periodically without prompting the user, so a 7-day expiry would
# silently fall off the user's calendar after a week. A year is the
# usual sweet spot — long enough to forget about, short enough that a
# leaked token has a bounded blast radius. Rotation invalidates earlier
# tokens by changing ``iat``.
_TOKEN_TTL = timedelta(days=365)


def _sign_token(*, user_id: str) -> tuple[str, datetime]:
    """Issue a fresh iCal token. Returns ``(token, expires_at)``.

    Raises ``RuntimeError`` if ``JWT_SECRET_KEY`` is not configured —
    a deployment without it is misconfigured and we don't want to
    silently issue valid-looking but unverifiable tokens.
    """
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    now = datetime.now(UTC)
    expires_at = now + _TOKEN_TTL
    payload = {
        "sub": user_id,
        "scope": _TOKEN_SCOPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        # Use a private audience so the standard Supabase JWT decode
        # path elsewhere won't accidentally accept this token.
        "aud": "equip-ical",
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_at


def _verify_token(token: str) -> str | None:
    """Return the ``sub`` (user id) if the token is valid and scoped
    to ``ical``. Returns ``None`` on any failure — never raises."""
    if not settings.JWT_SECRET_KEY:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience="equip-ical",
        )
    except jwt.PyJWTError as exc:
        logger.info("iCal token rejected: %s", exc)
        return None
    if payload.get("scope") != _TOKEN_SCOPE:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


@router.post(
    "/token",
    summary="Issue or rotate the caller's iCal subscription token",
    responses={
        200: {"description": "Returns the signed token + the subscribe URL."},
        503: {"description": "JWT_SECRET_KEY not configured on the deployment."},
    },
)
def issue_token(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Issue a fresh iCal token. Each call invalidates the previous
    token via the changed ``iat`` claim, so users who suspect their
    subscribe URL was leaked just call this again to rotate."""
    try:
        token, expires_at = _sign_token(user_id=str(current_user.id))
    except RuntimeError:
        raise equip_error(
            ErrorCode.TRANSLATION_WORKER_UNCONFIGURED,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            message="iCal export is not configured on this deployment",
            context={"resource_type": "calendar_ical"},
        ) from None
    # Build the feed URL against the request's own scheme/host so the
    # client always sees the same origin it just authenticated with —
    # no need for a static "public base url" config.
    feed_url = f"{request.url.scheme}://{request.url.netloc}{router.prefix}/feed?token={token}"
    return {
        "token": token,
        "feed_url": feed_url,
        "expires_at": expires_at.isoformat(),
    }


@router.get(
    "/feed",
    summary="iCal subscription feed (text/calendar)",
    response_class=Response,
    responses={
        200: {
            "description": "RFC 5545 calendar with the caller's upcoming module / assignment / course events.",
            "content": {"text/calendar": {}},
        },
        401: {"description": "Token missing, invalid, expired, or wrong scope."},
    },
)
def serve_feed(
    response: Response,
    token: str = Query(..., max_length=4096),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    db: Session = Depends(get_db),
) -> Response:
    user_id = _verify_token(token)
    if user_id is None:
        raise equip_error(
            ErrorCode.AUTH_REQUIRED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Invalid or expired iCal token",
            context={"resource_type": "calendar_ical"},
        )
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise equip_error(
            ErrorCode.AUTH_REQUIRED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Invalid iCal token subject",
            context={"resource_type": "calendar_ical"},
        ) from None
    user = db.query(User).filter(User.id == user_uuid).one_or_none()
    if user is None:
        # The token might have been issued before the account was
        # deleted; return 401 so the client unsubscribes rather than
        # caching an empty calendar.
        raise equip_error(
            ErrorCode.AUTH_REQUIRED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="iCal token references a deleted account",
            context={"resource_type": "calendar_ical"},
        )

    # Reuse the existing route logic so module deadlines + assignment
    # deadlines + course events all come through with the same cv
    # localization, source-locale fallback, deleted-course filtering,
    # and 1000-event cap. ``Response`` arg is unused but the upstream
    # route signature requires one.
    inner_response = Response()
    events: list[CalendarEvent] = get_calendar_events(
        response=inner_response,
        course_id=None,
        limit=1000,
        accept_language=accept_language,
        current_user=user,
        db=db,
    )
    body = render_calendar(events, user_email=user.email)
    response.headers["Content-Type"] = "text/calendar; charset=utf-8"
    response.headers["Cache-Control"] = "private, max-age=900"
    response.headers["Content-Disposition"] = 'inline; filename="equip-calendar.ics"'
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "private, max-age=900",
            "Content-Disposition": 'inline; filename="equip-calendar.ics"',
        },
    )
