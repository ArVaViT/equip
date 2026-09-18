"""Shapes for the legal documents and the record of accepting them."""

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas._request import RequestModel
from app.schemas.locale import LocaleCode


class LegalDocumentOut(BaseModel):
    """A document as served, with the fingerprint an acceptance will carry."""

    slug: str
    version: str
    locale: str
    body: str
    sha256: str


class LegalDocumentSummary(BaseModel):
    """What exists and at which version — enough to decide whether to ask.

    ``required_for`` and ``requires_consent`` come straight off the registry so
    the client never has to reconstruct either. A gate that decides for itself
    which documents a teacher owes is a gate that will disagree with the server
    the first time the two are edited apart.
    """

    slug: str
    version: str
    effective: date
    #: Roles that must accept it. Empty for a page nobody signs.
    required_for: list[str]
    #: Whether arriving at this version asks for a fresh acceptance, or is
    #: published and announced without one.
    requires_consent: bool


class LegalAcceptanceIn(RequestModel):
    """What the client claims to have shown, checked against what we serve.

    The body is deliberately absent. A client that supplies the text it says it
    displayed can supply any text; the server hashes its own copy, so the record
    attests to the document that actually exists.
    """

    slug: str
    version: str
    #: The reader's language, not the document's. It used to be pinned to the
    #: two languages the documents existed in, so a German reader could only
    #: consent by claiming to have read the Russian policy — and the record
    #: then said exactly that. The server answers with the language it
    #: actually served and stores that.
    locale: LocaleCode


class LegalNoticeIn(RequestModel):
    """Which notice somebody has just been shown and closed.

    No locale and no hash. A notice says "this document changed, here is what
    moved, here is the full text" — the reader is being told, not asked, and a
    record of a telling does not have to pin down which words were on screen.
    """

    slug: str
    version: str


class LegalAcceptanceOut(BaseModel):
    slug: str
    version: str
    locale: str
    accepted_at: datetime


class LegalStatusOut(BaseModel):
    """Whether this person still has something to accept, or to be told about.

    `outstanding` is the question the gate actually asks, answered once by the
    server rather than reconstructed by comparing lists on the client — where a
    mismatch shows up as a gate that will not close. It is answered for *this*
    person's role, which is how a promotion to teacher becomes a thing the
    client can notice without having re-read its own profile.

    `notices` is the other half of the promise: a document that changed without
    changing what anybody agreed to. The reader is told and not asked.
    """

    accepted: list[LegalAcceptanceOut]
    outstanding: list[LegalDocumentSummary]
    notices: list[LegalDocumentSummary]
