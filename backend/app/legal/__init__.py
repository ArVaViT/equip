"""The documents the platform asks people to accept, and the registry of them.

Until 2026-08 it asked for both and had neither. The first-run gate showed three
bullet points, a checkbox saying the reader had read and accepted the privacy
policy and the terms of use, and a line promising that the full version is
always available from the footer. There was no full version, no terms of use,
and no link in the footer. The acceptance was written to ``localStorage`` — so
clearing a browser erased every trace that anybody had ever agreed to anything,
which is the one job consent has.

Four decisions shape this package:

**The server owns the text.** The documents are files here, not strings in the
frontend bundle, because the hash recorded against an acceptance has to be a
hash of something the server can still produce. If the frontend held the text,
the record would attest to whatever the client claimed it had shown.

**Versions are explicit and additive.** Old versions are never edited in place —
an acceptance is a record of a specific text, and a text that can be rewritten
under it records nothing.

**A change that needs a signature says so in the data.** Each revision in
``LEGAL_REGISTRY`` carries ``consent``. A material change sets it and brings
everybody back to the gate; a correction does not and reaches people as a
notice. Which changes are material is defined inside each document's own text,
so the flag has a written rule behind it.

**Who signs what is also data.** ``required_for`` on a document is a set of
roles. The Teacher & Contributor Agreement is asked of teachers and directors
and of nobody else, and that is one field rather than a branch in a component.

**Four languages are one document.** A student who reads Ukrainian accepted the
Ukrainian text; that is what is stored. All four share a version, so "has this
person accepted the current privacy policy" has a single answer, and the
English text governs where the translations disagree.
"""

from app.legal.registry import (
    EVERYONE,
    GOVERNING_LOCALE,
    LEGAL_DOCUMENT_FINGERPRINTS,
    LEGAL_DOCUMENTS,
    LEGAL_REGISTRY,
    LOCALES,
    REFERENCE_DOCUMENTS,
    RUNS_A_SCHOOL,
    TEACHING,
    DocumentSpec,
    LegalDocument,
    Revision,
    document_for,
    document_spec,
    notices_for,
    outstanding_for,
    required_slugs,
)

__all__ = [
    "EVERYONE",
    "GOVERNING_LOCALE",
    "LEGAL_DOCUMENTS",
    "LEGAL_DOCUMENT_FINGERPRINTS",
    "LEGAL_REGISTRY",
    "LOCALES",
    "REFERENCE_DOCUMENTS",
    "RUNS_A_SCHOOL",
    "TEACHING",
    "DocumentSpec",
    "LegalDocument",
    "Revision",
    "document_for",
    "document_spec",
    "notices_for",
    "outstanding_for",
    "required_slugs",
]
