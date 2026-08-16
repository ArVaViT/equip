"""Which documents exist, at which version, and what they say."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DOCUMENTS_DIR = Path(__file__).parent / "documents"

#: The locales a document must exist in. A document missing one of these is a
#: broken deployment, not a fallback to English — half this school reads
#: Russian, and a policy they cannot read is not a policy they can accept.
LOCALES = ("ru", "en")

#: What a reader gets when these documents do not exist in their language.
#:
#: The platform speaks four languages and these documents exist in two, so
#: German and Ukrainian readers were being handed the *Russian* policy — a
#: text they cannot read, presented as the thing they are agreeing to. They
#: get English instead, which is the language this platform is governed in
#: and the same reason the certificate is English-only.
#:
#: Not a translation and not pretending to be one: the page says, in the
#: reader's own language, that the document it is showing is English. Having
#: these two documents professionally translated is the owner's call — a
#: machine-translated binding document would be worse than an honest one.
GOVERNING_LOCALE = "en"


@dataclass(frozen=True)
class LegalDocument:
    """One document, in one language, at one version."""

    slug: str
    version: str
    locale: str
    body: str

    @property
    def sha256(self) -> str:
        """The fingerprint stored against an acceptance.

        Computed from the bytes served, so a change of a single word in a
        published document is visible in the record afterwards — which is how
        "you agreed to this" stays a checkable claim rather than an assertion.
        """
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


#: slug -> version. Bumping a version here is what forces everyone to accept
#: again; it is deliberately a hand edit, because "material change" is a
#: judgement and not something a file mtime can decide.
LEGAL_DOCUMENTS: dict[str, str] = {
    "privacy": "1.0",
    "terms": "1.0",
}


def required_slugs() -> tuple[str, ...]:
    """What a person must have accepted to use the platform."""
    return tuple(LEGAL_DOCUMENTS)


@cache
def document_for(slug: str, locale: str) -> LegalDocument:
    """Load one document, or raise if it is missing.

    The returned document carries the locale it *is*, which is not always the
    locale that was asked for — a language these documents do not exist in
    gets the governing one. Every caller reads ``doc.locale`` rather than the
    request's, so the acceptance record says which text the person actually
    saw and the page can tell them which language they are reading.

    Cached because these are immutable files read on nearly every sign-in, and
    uncached because the cache is per-process — a deploy replaces the process,
    which is the only moment the files can change.
    """
    if slug not in LEGAL_DOCUMENTS:
        raise KeyError(f"unknown legal document: {slug}")
    served = locale if locale in LOCALES else GOVERNING_LOCALE
    path = DOCUMENTS_DIR / f"{slug}.{served}.md"
    if not path.is_file():
        # Deliberately fatal rather than falling back to another language:
        # one of the two required documents is missing from the build.
        raise FileNotFoundError(f"legal document missing from the build: {path.name}")
    return LegalDocument(
        slug=slug,
        version=LEGAL_DOCUMENTS[slug],
        locale=served,
        body=path.read_text(encoding="utf-8"),
    )
