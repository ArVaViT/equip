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

    Cached because these are immutable files read on nearly every sign-in, and
    uncached because the cache is per-process — a deploy replaces the process,
    which is the only moment the files can change.
    """
    if slug not in LEGAL_DOCUMENTS:
        raise KeyError(f"unknown legal document: {slug}")
    if locale not in LOCALES:
        raise KeyError(f"unsupported locale: {locale}")
    path = DOCUMENTS_DIR / f"{slug}.{locale}.md"
    if not path.is_file():
        # Deliberately fatal rather than falling back to another language.
        raise FileNotFoundError(f"legal document missing from the build: {path.name}")
    return LegalDocument(
        slug=slug,
        version=LEGAL_DOCUMENTS[slug],
        locale=locale,
        body=path.read_text(encoding="utf-8"),
    )
