"""Serving the documents, and recording that somebody accepted one."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.http import get_client_ip
from app.legal import (
    GOVERNING_LOCALE,
    LEGAL_REGISTRY,
    DocumentSpec,
    document_for,
    document_spec,
    notices_for,
    outstanding_for,
    required_slugs,
)
from app.legal.reference_notices import reference_notices_for
from app.models.legal_acceptance import LegalAcceptance
from app.models.legal_notice_seen import LegalNoticeSeen
from app.models.user import User
from app.schemas.legal import (
    LegalAcceptanceIn,
    LegalAcceptanceOut,
    LegalDocumentOut,
    LegalDocumentSummary,
    LegalNoticeIn,
    LegalStatusOut,
)

router = APIRouter(prefix="/legal", tags=["legal"])


def _summary(spec: DocumentSpec) -> LegalDocumentSummary:
    return LegalDocumentSummary(
        slug=spec.slug,
        version=spec.current.version,
        effective=spec.current.effective,
        required_for=sorted(spec.required_for),
        requires_consent=spec.current.consent,
    )


@router.get("/documents", response_model=list[LegalDocumentSummary])
def list_documents() -> list[LegalDocumentSummary]:
    """What must be accepted, by whom, and at which version. Public on purpose.

    Every signable document, not only the ones the caller owes: this route has
    no caller to ask about, and a person deciding whether to sign up is
    entitled to see the agreement they would be under if they ever taught here.
    Which of them *this* person still owes is
    :func:`my_acceptances`, which does know who is asking.
    """
    return [_summary(spec) for spec in LEGAL_REGISTRY if spec.signable]


@router.get("/documents/{slug}", response_model=LegalDocumentOut)
def get_document(slug: str, locale: str = GOVERNING_LOCALE) -> LegalDocumentOut:
    """One document, in one language.

    Unauthenticated by design: a person deciding whether to sign up has to be
    able to read what they would be agreeing to, and a policy you can only see
    after accepting it is not a policy.

    ``locale`` is what the reader asked for; the response's ``locale`` is what
    they got, and the two differ only for a language these documents do not
    exist in — which, since 2026-09-17, is no language the interface serves.
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


def _last_agreed_on(rows: list[LegalAcceptance]) -> date | None:
    """The day this person most recently agreed to anything, or ``None``.

    What a change to a reference page is measured against. Somebody who has
    agreed to nothing is about to meet the gate and does not need a banner in
    front of it.
    """
    if not rows:
        return None
    return max(row.accepted_at for row in rows).date()


def _accepted_rows(db: Session, user_id: uuid.UUID) -> list[LegalAcceptance]:
    return list(db.scalars(select(LegalAcceptance).where(LegalAcceptance.user_id == user_id)).all())


@router.get("/acceptances/me", response_model=LegalStatusOut)
def my_acceptances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LegalStatusOut:
    """What this person has accepted, still owes, and should be told about.

    The role is read from the database row rather than taken from the client,
    which makes this route the place a promotion becomes visible. A tab left
    open while an administrator grants the teaching role keeps a stale profile
    — nothing in the frontend re-reads it — but this answer changes on the next
    poll, and the teacher agreement appearing in ``outstanding`` is how the
    application finds out.
    """
    rows = _accepted_rows(db, current_user.id)
    accepted = {(row.document_slug, row.version) for row in rows}
    role = current_user.role
    # A notice is shown until it has been read, and then not again — on this
    # device or any other. A browser flag would re-show it on the laptop after
    # it was closed on the phone, which teaches people to dismiss banners
    # without reading them: the failure this whole mechanism exists to avoid,
    # one notch quieter.
    told = {
        (row.document_slug, row.version)
        for row in db.scalars(select(LegalNoticeSeen).where(LegalNoticeSeen.user_id == current_user.id)).all()
    }
    owed = outstanding_for(role, accepted)
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
        outstanding=[_summary(spec) for spec in owed],
        # Two kinds of telling, one list, because the reader is not being asked
        # to care about the difference. ``notices_for`` answers for the
        # documents they signed; ``reference_notices_for`` answers for the
        # pages those documents point at — the supplier list above all, where
        # the policy promises to say when it moves and until now said nothing,
        # because a notice mechanism built out of ``required_slugs`` could
        # never reach a document nobody is required to sign.
        #
        # ``owed`` goes in so the second kind stays quiet while the consent
        # gate is up: a banner about a page nobody signs, next to a dialog
        # demanding a signature, is two claims on attention for one change.
        notices=[
            _summary(spec)
            for spec in (*notices_for(role, accepted), *reference_notices_for(_last_agreed_on(rows), told, owed))
            if (spec.slug, spec.current.version) not in told
        ],
    )


@router.post("/acceptances", response_model=LegalAcceptanceOut, status_code=status.HTTP_201_CREATED)
def accept(
    payload: LegalAcceptanceIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LegalAcceptanceOut:
    """Record an acceptance of a document the server can still produce."""
    # Only the documents that are actually asked for can be accepted. The same
    # route serves reference pages — the provider list the privacy policy
    # points at — and those are read, never signed: a row in
    # ``legal_acceptances`` asserting agreement to a page nobody was ever asked
    # to agree to makes the table harder to read and answers a question nobody
    # posed.
    #
    # Signable for *anybody*, deliberately, rather than signable for this
    # person's role. A promotion and a gate can race — an administrator grants
    # the teaching role, the client is shown the agreement, an administrator
    # changes their mind — and refusing the acceptance in that window would
    # leave a person who has read and ticked the thing with nowhere to put it.
    # An extra row is harmless; a missing one is the failure this table exists
    # to prevent.
    if payload.slug not in required_slugs():
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message=f"'{payload.slug}' is not a document that requires acceptance",
            context={"resource_type": "legal_document", "resource_id": payload.slug},
        )

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
        # Named in the privacy policy itself, and stored at this moment and at
        # a submission declaration and nowhere else: it is evidence that the
        # acceptance happened.
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


@router.post("/notices/seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_notice_seen(
    payload: LegalNoticeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Record that somebody has been told about a notice-only change.

    Deliberately not an acceptance and deliberately not on the acceptance
    route. The row this writes asserts "they were told", which is a weaker
    claim than "they agreed" and has to stay weaker: a consent table that also
    holds dismissals answers its own question ambiguously.

    No 409 for a version we no longer serve, unlike accepting. A stale tab
    closing a banner about a superseded version is closing a banner; there is
    nothing to get wrong, and refusing it would leave it on screen forever.
    """
    try:
        spec = document_spec(payload.slug)
    except KeyError as exc:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Legal document '{payload.slug}' not found",
            context={"resource_type": "legal_document", "resource_id": payload.slug},
        ) from exc

    db.add(LegalNoticeSeen(user_id=current_user.id, document_slug=spec.slug, version=payload.version))
    try:
        db.commit()
    except IntegrityError:
        # Two tabs, or a double-click. Being told twice is being told.
        db.rollback()
