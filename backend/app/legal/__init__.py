"""The documents the platform asks people to accept, and the registry of them.

Until now it asked for both and had neither. The first-run gate showed three
bullet points, a checkbox saying the reader had read and accepted the privacy
policy and the terms of use, and a line promising that the full version is
always available from the footer. There was no full version, no terms of use,
and no link in the footer. The acceptance was written to
``localStorage`` — so clearing a browser erased every trace that anybody had
ever agreed to anything, which is the one job consent has.

Three decisions shape this package:

**The server owns the text.** The documents are files here, not strings in the
frontend bundle, because the hash recorded against an acceptance has to be a
hash of something the server can still produce. If the frontend held the text,
the record would attest to whatever the client claimed it had shown.

**Versions are explicit and additive.** A material change means a new version
and a fresh acceptance. Old versions are never edited in place — an acceptance
is a record of a specific text, and a text that can be rewritten under it
records nothing.

**Two languages are one document.** A student who reads Russian accepted the
Russian text; that is what is stored. But both translations share a version, so
"has this person accepted the current privacy policy" has a single answer.
"""

from app.legal.registry import (
    GOVERNING_LOCALE,
    LEGAL_DOCUMENTS,
    LegalDocument,
    document_for,
    required_slugs,
)

__all__ = [
    "GOVERNING_LOCALE",
    "LEGAL_DOCUMENTS",
    "LegalDocument",
    "document_for",
    "required_slugs",
]
