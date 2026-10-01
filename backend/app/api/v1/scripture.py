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

One request per lesson, not per block: the page gathers its blocks' texts
and sends them together (a class on one church Wi-Fi shares one IP and its
rate limit). Signed-in only, and bounded: the text is capped and so is the
number of distinct references, and the ones not yet cached are fetched from
YouVersion side by side rather than one after another.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import get_current_user
from app.models.user import User  # noqa: TC001
from app.schemas.locale import normalize_locale
from app.services.bible.api_source import API_BIBLE_IDS, fetch_verse
from app.services.bible.references import BibleRef, parse_references
from app.services.bible.store import lookup

router = APIRouter(prefix="/scripture", tags=["scripture"])

#: A long lesson is a few tens of thousands of characters, all blocks together.
MAX_TEXT = 60_000
MAX_TEXTS = 100
#: Distinct references answered per request. A block citing more than this
#: is a reference list, and the rest stay plain text.
MAX_REFERENCES = 40

#: Verses fetched at once. Each is one short HTTPS call, cached for the
#: life of the process once answered.
FETCH_AT_ONCE = 8

#: Which edition a text came from, as a key the page turns into a name.
_API_EDITION = {"en": "bsb", "ru": "nrt", "de": "elberfelder", "uk": "kulish"}


class ScriptureTexts(BaseModel):
    texts: list[str] = Field(..., max_length=MAX_TEXTS, description="Each block's text, in order")

    @field_validator("texts")
    @classmethod
    def _not_too_much(cls, texts: list[str]) -> list[str]:
        if sum(len(t) for t in texts) > MAX_TEXT:
            raise ValueError(f"at most {MAX_TEXT} characters in all")
        return texts


class Passage(BaseModel):
    written: str = Field(..., description="The reference exactly as the lesson writes it")
    ref: str = Field(..., description="Canonical form, e.g. 'acts 1:8'")
    text: str
    edition: str = Field(..., description="Edition key: bsb, kjv, nrt, elberfelder, kulish")


def _verse(ref: BibleRef, locale: str) -> tuple[str | None, str]:
    """Same choice as ``canonical_for_display``, spelled out so the card can
    name the edition: the API's, then the King James file for English only.
    The Russian file is misaligned (#990) and never shown."""
    text = fetch_verse(ref, locale) if locale in API_BIBLE_IDS else None  # type: ignore[arg-type]
    if text is None and locale == "en":
        return lookup(ref, "en"), "kjv"
    return text, _API_EDITION.get(locale, "")


@router.post("/passages", response_model=list[list[Passage]])
def find_passages(
    body: ScriptureTexts,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    _user: User = Depends(get_current_user),
) -> list[list[Passage]]:
    """For each text, the references in it that can be shown, with their verse text."""
    response.headers["Vary"] = "Accept-Language"
    locale = normalize_locale(accept_language, fallback="en")

    found = [parse_references(text, locale) for text in body.texts]
    refs: dict[str, BibleRef] = {}
    for parsed in (p for block in found for p in block):
        if len(refs) >= MAX_REFERENCES:
            break
        refs.setdefault(str(parsed.ref), parsed.ref)
    with ThreadPoolExecutor(max_workers=FETCH_AT_ONCE) as pool:
        verses = dict(zip(refs, pool.map(lambda r: _verse(r, locale), refs.values()), strict=True))

    out: list[list[Passage]] = []
    for block in found:
        passages: list[Passage] = []
        seen: set[str] = set()
        for parsed in block:
            key = str(parsed.ref)
            text, edition = verses.get(key, (None, ""))
            if not text or parsed.raw_text in seen:
                continue
            seen.add(parsed.raw_text)
            passages.append(Passage(written=parsed.raw_text, ref=key, text=text, edition=edition))
        out.append(passages)
    return out
