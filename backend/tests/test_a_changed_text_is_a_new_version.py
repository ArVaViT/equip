"""A legal document that changes is a new version, or it is not a change we make.

Production has two different ``content_sha256`` values for each of the two
documents at version 1.0. The texts were edited after people had accepted
them and the version was left alone, so "accepted privacy 1.0" no longer
names one text. Each acceptance row still carries the hash it was given, so
nothing is lost — but the version stopped meaning anything, and the version
is what the gate compares.

This test is the guard: every document served is hashed and compared with the
fingerprint pinned in the registry. Changing a file without moving the version
fails here, with the two things the author has to do spelled out.
"""

from __future__ import annotations

from app.legal import LEGAL_DOCUMENT_FINGERPRINTS, LEGAL_DOCUMENTS, document_for
from app.legal.registry import LOCALES


def test_every_served_text_matches_its_pinned_fingerprint() -> None:
    for slug, version in LEGAL_DOCUMENTS.items():
        for locale in LOCALES:
            doc = document_for(slug, locale)
            pinned = LEGAL_DOCUMENT_FINGERPRINTS.get((slug, version, locale))
            assert pinned is not None, (
                f"{slug} {version} ({locale}) has no fingerprint in LEGAL_DOCUMENT_FINGERPRINTS. "
                f"Add ({slug!r}, {version!r}, {locale!r}): {doc.sha256!r}."
            )
            assert doc.sha256 == pinned, (
                f"{slug}.{locale}.md changed but LEGAL_DOCUMENTS[{slug!r}] is still {version!r}. "
                "People have accepted the old text under this version. Either revert the edit, "
                f"or bump the version and pin the new text: ({slug!r}, <new version>, {locale!r}): {doc.sha256!r}."
            )


def test_the_current_version_of_every_document_is_pinned() -> None:
    current = {(slug, version, locale) for slug, version in LEGAL_DOCUMENTS.items() for locale in LOCALES}
    assert current <= set(LEGAL_DOCUMENT_FINGERPRINTS)
