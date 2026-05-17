"""Verse-of-the-day route.

Single public endpoint. No auth — same verse for everyone — so it can
also be hit from the unauthenticated marketing page in the future. When
the upstream YouVersion service is unreachable or the API key is
missing, returns 404 so the frontend can hide the card gracefully.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query, status

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
    locale: str = Query(
        default="en",
        description="Locale to render the verse in (e.g. 'en', 'ru', 'en-US').",
    ),
) -> VerseOfTheDayResponse:
    """Return today's curated verse, localized."""
    normalized: LocaleCode = normalize_locale(locale, fallback="en")
    try:
        verse = get_verse_of_the_day(normalized)
    except VerseOfTheDayUnavailable as exc:
        # 404 is more polite than 503 here: from the caller's perspective
        # there is just "no verse for you right now" and they should hide
        # the card. Logging stays at INFO since the route can legitimately
        # serve 404 in CI / preview deployments without the API key.
        logger.info("Verse of the day unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="verse_of_the_day_unavailable",
        ) from None

    return VerseOfTheDayResponse(
        reference=verse.reference,
        text=verse.text,
        version=verse.version,
        locale=verse.locale,
        date=verse.date,
    )
