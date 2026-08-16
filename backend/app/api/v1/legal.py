"""Serving the documents, and recording that somebody accepted one."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.http import get_client_ip
from app.legal import GOVERNING_LOCALE, LEGAL_DOCUMENTS, document_for, required_slugs
from app.models.legal_acceptance import LegalAcceptance
from app.models.user import User
from app.schemas.legal import (
    LegalAcceptanceIn,
    LegalAcceptanceOut,
    LegalDocumentOut,
    LegalDocumentSummary,
    LegalStatusOut,
)

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/documents", response_model=list[LegalDocumentSummary])
def list_documents() -> list[LegalDocumentSummary]:
    """What must be accepted, and at which version. Public on purpose."""
    return [LegalDocumentSummary(slug=slug, version=version) for slug, version in LEGAL_DOCUMENTS.items()]


@router.get("/documents/{slug}", response_model=LegalDocumentOut)
def get_document(slug: str, locale: str = GOVERNING_LOCALE) -> LegalDocumentOut:
    """One document, in one language.

    Unauthenticated by design: a person deciding whether to sign up has to be
    able to read what they would be agreeing to, and a policy you can only see
    after accepting it is not a policy.

    ``locale`` is what the reader asked for; the response's ``locale`` is what
    they got, and the two differ for a language these documents do not exist
    in. The default used to be Russian, which meant a bare request — and every
    reader whose language was not English — was answered in a language they
    may not read.
    """
    try:
        doc = document_for(slug, locale)
    except (KeyError, FileNotFoundError) as exc:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Legal document '{slug}' not found",
            context={"resource_type": "legal_document", "resource_id": slug},
        ) from exc
    return LegalDocumentOut(
        slug=doc.slug,
        version=doc.version,
        locale=doc.locale,
        body=doc.body,
        sha256=doc.sha256,
    )


def _accepted_rows(db: Session, user_id) -> list[LegalAcceptance]:
    return list(db.scalars(select(LegalAcceptance).where(LegalAcceptance.user_id == user_id)).all())


@router.get("/acceptances/me", response_model=LegalStatusOut)
def my_acceptances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LegalStatusOut:
    rows = _accepted_rows(db, current_user.id)
    current = {(slug, version) for slug, version in LEGAL_DOCUMENTS.items()}
    have = {(row.document_slug, row.version) for row in rows}
    outstanding = [
        LegalDocumentSummary(slug=slug, version=version)
        for slug, version in sorted(current - have)
        if slug in required_slugs()
    ]
    return LegalStatusOut(
        accepted=[
            LegalAcceptanceOut(
                slug=row.document_slug,
                version=row.version,
                locale=row.locale,
                accepted_at=row.accepted_at,
            )
            for row in rows
        ],
        outstanding=outstanding,
    )


@router.post("/acceptances", response_model=LegalAcceptanceOut, status_code=status.HTTP_201_CREATED)
def accept(
    payload: LegalAcceptanceIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LegalAcceptanceOut:
    """Record an acceptance of a document the server can still produce."""
    try:
        doc = document_for(payload.slug, payload.locale)
    except (KeyError, FileNotFoundError) as exc:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Legal document '{payload.slug}' not found",
            context={"resource_type": "legal_document", "resource_id": payload.slug},
        ) from exc

    # A client accepting a version we no longer serve has a stale page open.
    # Recording it would produce a row asserting agreement to a text nobody can
    # now produce — the exact failure this table exists to prevent.
    if payload.version != doc.version:
        raise equip_error(
            ErrorCode.LEGAL_DOCUMENT_CHANGED,
            status_code=status.HTTP_409_CONFLICT,
            message="This document has changed since the page was loaded",
            context={"slug": doc.slug, "current_version": doc.version},
        )

    row = LegalAcceptance(
        user_id=current_user.id,
        document_slug=doc.slug,
        version=doc.version,
        locale=doc.locale,
        content_sha256=doc.sha256,
        ip=get_client_ip(request),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Already accepted this exact version — a double-click, or a second
        # tab. Not new consent, and not an error worth showing anybody.
        db.rollback()
        existing = db.scalars(
            select(LegalAcceptance).where(
                LegalAcceptance.user_id == current_user.id,
                LegalAcceptance.document_slug == doc.slug,
                LegalAcceptance.version == doc.version,
            )
        ).one()
        return LegalAcceptanceOut(
            slug=existing.document_slug,
            version=existing.version,
            locale=existing.locale,
            accepted_at=existing.accepted_at,
        )
    db.refresh(row)
    return LegalAcceptanceOut(
        slug=row.document_slug,
        version=row.version,
        locale=row.locale,
        accepted_at=row.accepted_at,
    )
