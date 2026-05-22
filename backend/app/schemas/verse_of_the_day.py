"""Public API shape for the verse-of-the-day endpoint.

A single response model — kept colocated with other schemas so the
OpenAPI doc generator picks it up by package convention.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Pydantic v2 needs ``LocaleCode`` (a ``Literal[...]``) at runtime to build
# the validator, so it cannot move into a ``TYPE_CHECKING`` block.
from app.schemas.locale import LocaleCode  # noqa: TC001


class VerseOfTheDayResponse(BaseModel):
    """One scripture passage rendered in the caller's locale.

    The ``reference`` is the localized form returned by the upstream
    Bible API — ``John 3:16`` in English, ``От Иоанна 3:16`` in Russian —
    so the frontend never has to translate book names.
    """

    reference: str = Field(..., description="Localized passage reference")
    text: str = Field(..., description="Verse text, plain (no markup)")
    version: str = Field(..., description="Bible translation abbreviation")
    locale: LocaleCode = Field(..., description="Locale the text is rendered in")
    date: str = Field(..., description="ISO-8601 UTC date this verse is for")
