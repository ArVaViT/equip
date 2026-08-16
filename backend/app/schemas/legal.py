"""Shapes for the legal documents and the record of accepting them."""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.locale import LocaleCode


class LegalDocumentOut(BaseModel):
    """A document as served, with the fingerprint an acceptance will carry."""

    slug: str
    version: str
    locale: str
    body: str
    sha256: str


class LegalDocumentSummary(BaseModel):
    """What exists and at which version — enough to decide whether to ask."""

    slug: str
    version: str


class LegalAcceptanceIn(BaseModel):
    """What the client claims to have shown, checked against what we serve.

    The body is deliberately absent. A client that supplies the text it says it
    displayed can supply any text; the server hashes its own copy, so the record
    attests to the document that actually exists.
    """

    slug: str
    version: str
    #: The reader's language, not the document's. It used to be pinned to the
    #: two languages the documents exist in, so a German reader could only
    #: consent by claiming to have read the Russian policy — and the record
    #: then said exactly that. The server answers with the language it
    #: actually served and stores that.
    locale: LocaleCode


class LegalAcceptanceOut(BaseModel):
    slug: str
    version: str
    locale: str
    accepted_at: datetime


class LegalStatusOut(BaseModel):
    """Whether this person still has something to accept.

    `outstanding` is the question the first-run gate actually asks, answered
    once by the server rather than reconstructed by comparing two lists on the
    client — where a mismatch shows up as a gate that will not close.
    """

    accepted: list[LegalAcceptanceOut]
    outstanding: list[LegalDocumentSummary]
