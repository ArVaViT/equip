"""The verses a lesson cites, in the reader's own Bible, for the card a tap opens.

Looking a verse up is the commonest thing a student does in a Bible lesson,
and until now it meant leaving the lesson for another app. The page sends
the text of a lesson block; this finds the references in it with the same
parser the translation pipeline trusts (``parse_references``) — so the page
does not keep a second, weaker list of book names — and answers each with
the canonical text for the reader's language (``canonical_for_display``).

A reference with no text to show is left out rather than answered with
``null``: the page links only what it can open. That covers a language with
no edition, a local or preview build without the API key, and a psalm whose
numbering does not map, exactly as the lesson body itself behaves.

Signed-in only, and bounded: the text is capped and so is the number of
distinct references, since each one not yet cached is a call to YouVersion.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.models.user import User  # noqa: TC001
from app.schemas.locale import normalize_locale
from app.services.bible.api_source import API_BIBLE_IDS, fetch_verse
from app.services.bible.references import parse_references
from app.services.bible.store import lookup

router = APIRouter(prefix="/scripture", tags=["scripture"])

#: A long lesson block is a few thousand characters; this is generous.
MAX_TEXT = 100_000
#: Distinct references answered per request. A block citing more than this
#: is a reference list, and the rest stay plain text.
MAX_REFERENCES = 40

#: Which edition a text came from, as a key the page turns into a name.
_API_EDITION = {"en": "bsb", "ru": "nrt", "de": "elberfelder", "uk": "kulish"}


class ScriptureText(BaseModel):
    text: str = Field(..., max_length=MAX_TEXT)


class Passage(BaseModel):
    written: str = Field(..., description="The reference exactly as the lesson writes it")
    ref: str = Field(..., description="Canonical form, e.g. 'acts 1:8'")
    text: str
    edition: str = Field(..., description="Edition key: bsb, kjv, nrt, elberfelder, kulish")


@router.post("/passages", response_model=list[Passage])
def find_passages(
    body: ScriptureText,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    _user: User = Depends(get_current_user),
) -> list[Passage]:
    """Every reference in ``text`` that can be shown, with its verse text."""
    response.headers["Vary"] = "Accept-Language"
    locale = normalize_locale(accept_language, fallback="en")
    found: list[Passage] = []
    seen: set[str] = set()
    for parsed in parse_references(body.text, locale):
        if parsed.raw_text in seen:
            continue
        seen.add(parsed.raw_text)
        if len(seen) > MAX_REFERENCES:
            break
        # Same choice as ``canonical_for_display``, spelled out so the card
        # can name the edition: the API's, then the King James file for
        # English only. The Russian file is misaligned (#990) and never shown.
        text = fetch_verse(parsed.ref, locale) if locale in API_BIBLE_IDS else None
        edition = _API_EDITION.get(locale, "")
        if text is None and locale == "en":
            text = lookup(parsed.ref, "en")
            edition = "kjv"
        if not text:
            continue
        found.append(Passage(written=parsed.raw_text, ref=str(parsed.ref), text=text, edition=edition))
    return found
