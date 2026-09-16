"""Pre-accept the required legal documents for the e2e role users.

``GET /legal/acceptances/me`` (``app/api/v1/legal.py``) tells the frontend's
``FirstRunFlow`` whether a document in ``required_slugs()`` (currently
``privacy`` + ``terms``) is outstanding for the signed-in user. A freshly
created CI role user has no ``legal_acceptances`` rows at all, so the server
truthfully reports both as outstanding — and ``FirstRunFlow`` opens its
full-screen consent dialog on top of every page, exactly as it would for a
real new signup.

That dialog intercepts pointer events (z-index above everything, including
the tour overlay), which is what broke ``teacher-flow.spec.ts``'s analytics
click: ``global.setup.ts``'s ``suppressOnboarding`` only fakes the
``localStorage`` cache flag (``equip.privacy.accepted.<userId>``), but
``FirstRunFlow`` treats that cache as provisional and overwrites it the
moment ``legalService.status()`` answers from the server — see
``decideInitialStep`` / the effect in ``FirstRunFlow.tsx``. A client-side
flag can outrun a real server round-trip; it can't out-argue one.

This script writes the real rows instead, the same way ``POST
/legal/acceptances`` would for someone who clicked "I agree": one row per
``required_slugs()`` document, in the governing locale, with the document's
actual current ``sha256`` (``app.legal.document_for``) — not a placeholder,
because ``content_sha256`` is what makes the row a checkable claim rather
than an assertion. Idempotent: the unique constraint on
``(user_id, document_slug, version)`` means a re-run against the same users
is a no-op.

Usage::

    python -m scripts.seed_e2e_legal_acceptance <user_id> [<user_id> ...]
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.legal import GOVERNING_LOCALE, document_for, required_slugs
from app.models.legal_acceptance import LegalAcceptance

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_e2e_legal_acceptance")


def accept_all(db, *, user_id: uuid.UUID) -> None:
    for slug in required_slugs():
        doc = document_for(slug, GOVERNING_LOCALE)
        existing = (
            db.query(LegalAcceptance)
            .filter(
                LegalAcceptance.user_id == user_id,
                LegalAcceptance.document_slug == doc.slug,
                LegalAcceptance.version == doc.version,
            )
            .one_or_none()
        )
        if existing is not None:
            logger.info("%s already accepted %s %s; skipping", user_id, doc.slug, doc.version)
            continue
        db.add(
            LegalAcceptance(
                user_id=user_id,
                document_slug=doc.slug,
                version=doc.version,
                locale=doc.locale,
                content_sha256=doc.sha256,
                ip=None,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            # Concurrent run already wrote it (unique on user/slug/version).
            db.rollback()
        else:
            logger.info("Recorded %s acceptance of %s %s", user_id, doc.slug, doc.version)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_ids", nargs="+", help="Profile UUIDs to mark as having accepted every required document")
    args = parser.parse_args()

    try:
        user_ids = [uuid.UUID(raw) for raw in args.user_ids]
    except ValueError as exc:
        logger.error("Every argument must be a UUID: %s", exc)
        return 1

    engine = _get_engine()
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with session_factory() as db:
        for user_id in user_ids:
            accept_all(db, user_id=user_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
