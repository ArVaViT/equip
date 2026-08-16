"""Verse-of-the-day route.

Single public endpoint. No auth — same verse for everyone — so it can
also be hit from the unauthenticated marketing page in the future. When
the upstream YouVersion service is unreachable or the API key is
missing, returns 404 so the frontend can hide the card gracefully.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, Query, Response, status

from app.core.errors import ErrorCode, equip_error
from app.schemas.locale import normalize_locale
from app.schemas.verse_of_the_day import VerseOfTheDayResponse
from app.services.verse_of_the_day import (
    VerseOfTheDayUnavailable,
    get_verse_of_the_day,
)

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/verse-of-the-day", tags=["verse-of-the-day"])


@router.get("", response_model=VerseOfTheDayResponse)
def read_verse_of_the_day(
    response: Response,
    locale: str | None = Query(
        default=None,
        description="Locale to render the verse in (e.g. 'en', 'ru', 'en-US'). Defaults to Accept-Language.",
    ),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> VerseOfTheDayResponse:
    """Return today's curated verse, localized.

    The explicit parameter wins — the web app sends it, because its
    language is a stored preference rather than whatever the browser
    announces. Everything else on the platform reads ``Accept-Language``,
    though, and this route used to ignore it and answer English: a
    Russian reader calling it without the parameter got an English
    verse, silently, and so did every other client.
    """
    response.headers["Vary"] = "Accept-Language"
    normalized: LocaleCode = normalize_locale(locale or accept_language, fallback="en")
    try:
        verse = get_verse_of_the_day(normalized)
    except VerseOfTheDayUnavailable as exc:
        # 404 is more polite than 503 here: from the caller's perspective
        # there is just "no verse for you right now" and they should hide
        # the card. Logging stays at INFO since the route can legitimately
        # serve 404 in CI / preview deployments without the API key.
        logger.info("Verse of the day unavailable: %s", exc)
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="verse_of_the_day_unavailable",
            context={"resource_type": "verse_of_the_day"},
        ) from None

    return VerseOfTheDayResponse(
        reference=verse.reference,
        text=verse.text,
        version=verse.version,
        locale=verse.locale,
        date=verse.date,
    )
