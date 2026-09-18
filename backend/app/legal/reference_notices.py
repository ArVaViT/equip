"""Telling people when the supplier list changes.

The privacy policy names no suppliers. It points at ``providers``, a page that
is read and never signed, and says that changing which company holds the
database this quarter is housekeeping rather than a new promise. That split is
right, and it was argued for at length in the registry: making a supplier swap
a version bump would bring a hundred people back to a consent screen over
something none of them agreed to in the first place, and a consent screen
people meet over housekeeping is a consent screen people stop reading.

But "you do not have to agree again" is not "you do not get to know". Under
GDPR Art. 28(2) a controller who gives general authorisation for sub-processors
has to be *informed* of additions and replacements, and be able to object. The
policy makes that promise. Nothing kept it: ``notices_for`` walks
``required_slugs(role)``, which by construction holds only the documents
somebody signs — so the one document class the notice mechanism was needed for
was the one class it could never reach. Changing the provider list told nobody.

This module is the missing half. Same mechanism, same banner, same
``legal_notices_seen`` row; the only new thing is deciding *who* a change is
news to.

Who is told
-----------

Somebody who has agreed to something here, and whose agreement predates the
change. Two consequences, both deliberate:

* A person signing up today is not told the list "changed" — they are meeting
  it for the first time, on the screen that links to it. A banner announcing a
  change to somebody who has never seen the unchanged version is noise, and
  noise is what trains people to close banners unread.
* A person who accepted in August and comes back in October is told, once,
  because for them it did change.

The comparison is against the date of their most recent acceptance rather than
against a stored "providers version I was shown". No new column for a question
the two existing tables already answer between them, and no backfill inventing
an answer for the rows that predate the question.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003  (runtime annotation)

from app.legal.registry import LEGAL_REGISTRY, DocumentSpec


def reference_notices_for(
    last_agreed_on: date | None,
    seen: set[tuple[str, str]],
) -> tuple[DocumentSpec, ...]:
    """Pages this person reads but never signs, that changed after they agreed.

    ``last_agreed_on`` is the date of their most recent acceptance of anything,
    or ``None`` for somebody who has agreed to nothing yet — who is about to
    meet the gate and does not need a banner in front of it.

    ``seen`` is every ``(slug, version)`` already in ``legal_notices_seen`` for
    them, so a banner closed on a phone is not waiting on the laptop.

    A reference page with only its original revision is never news: there is
    nothing to have changed. That falls out of the date comparison, since the
    first revision cannot post-date an acceptance made after it — but it is
    stated here because it is the property that keeps a fresh deployment quiet.
    """
    if last_agreed_on is None:
        return ()
    return tuple(
        spec
        for spec in LEGAL_REGISTRY
        if not spec.signable
        and len(spec.revisions) > 1
        and spec.current.effective > last_agreed_on
        and (spec.slug, spec.current.version) not in seen
    )


__all__ = ["reference_notices_for"]
