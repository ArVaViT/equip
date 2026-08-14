"""Is this course translated? — the question publication has to answer.

The rule is Vadym's, and it is not a preference: a course does not go
out until every language has it, and not merely translated but checked
— nothing mixed up, nothing lost, everything in its place. A platform
whose whole promise is that a German writes a course and Ukrainians and
Americans take it cannot ship a course that is whole in one language
and partial in another. That is not a smaller feature for the second
group; it is a different course.

What "translated" means here
----------------------------

For every translatable field of every entity under the course — walked
by ``course_tree``, with the field list and per-field source language
from ``registry.entity_field_specs`` — there must be an active
``content_versions`` row with ``status='ok'`` in every supported locale
other than that field's own source.

Three ways it can be missing, and they are different problems:

* ``missing`` — no row at all. The pipeline has not got here yet, or
  the field was edited and the new text has not been translated.
* ``needs_review`` — a translation came back and failed the structural
  check (``validation.py``). A person has to look at it.
* ``failed`` — the provider call did not produce text. Retryable, or
  terminal at ``failed_permanent``.

Reported separately because they need different work: waiting, reading,
and retrying are not the same thing, and a teacher staring at "not
ready" deserves to know which one they are in.

Cost
----

One walk of the tree (already bulk-fetched) plus one query for the
content rows of everything it yielded. It is meant to be affordable on
the publish path and in the readiness panel, not only in a cron.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import tuple_

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import CourseStatus
from app.schemas.locale import LOCALE_CODES
from app.services.translation.course_tree import iter_course_entities
from app.services.translation.registry import entity_field_specs
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course

logger = logging.getLogger(__name__)

GapReason = Literal["missing", "needs_review", "failed"]


@dataclass(frozen=True, slots=True)
class TranslationGap:
    """One (entity, field, locale) that is not servable yet."""

    entity_type: str
    entity_id: str
    field: str
    locale: str
    reason: GapReason


@dataclass(frozen=True, slots=True)
class TranslationCompleteness:
    """What the publication gate needs to decide, and what the UI needs
    to explain the decision."""

    required: int
    present: int
    gaps: tuple[TranslationGap, ...]

    @property
    def is_complete(self) -> bool:
        return not self.gaps

    def by_reason(self, reason: GapReason) -> tuple[TranslationGap, ...]:
        return tuple(gap for gap in self.gaps if gap.reason == reason)

    def by_locale(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for gap in self.gaps:
            counts[gap.locale] += 1
        return dict(counts)


_REASON_BY_STATUS: dict[str, GapReason] = {
    ContentVersionStatus.NEEDS_REVIEW: "needs_review",
    ContentVersionStatus.FAILED: "failed",
    ContentVersionStatus.FAILED_PERMANENT: "failed",
}


def course_translation_completeness(db: Session, course: Course) -> TranslationCompleteness:
    """Return what is translated under ``course`` and what is not.

    ``required`` counts (field, locale) pairs that must exist;
    ``present`` counts those that do, with ``status='ok'``.
    """
    if not is_translation_enabled():
        # No provider configured — local development, CI, a deploy
        # without a Gemini key. Nothing will ever translate this course,
        # so requiring translations would mean nothing could ever be
        # published. The gate exists to keep a half-translated course
        # out of the catalog, not to make the catalog unreachable.
        return TranslationCompleteness(required=0, present=0, gaps=())

    # (entity_type, entity_id, field) -> {target locale, …}
    wanted: dict[tuple[str, str, str], set[str]] = {}

    for entity_type, entity in iter_course_entities(db, course):
        entity_id = str(entity.id)  # type: ignore[attr-defined]
        for spec in entity_field_specs(db, entity_type, entity, course):
            targets: set[str] = {code for code in LOCALE_CODES if code != spec.source_locale}
            if not targets:
                continue
            wanted[(entity_type, entity_id, spec.field)] = targets

    if not wanted:
        return TranslationCompleteness(required=0, present=0, gaps=())

    rows = (
        db.query(
            ContentVersion.entity_type,
            ContentVersion.entity_id,
            ContentVersion.field,
            ContentVersion.locale,
            ContentVersion.status,
        )
        .filter(
            tuple_(
                ContentVersion.entity_type,
                ContentVersion.entity_id,
                ContentVersion.field,
            ).in_(list(wanted)),
            ContentVersion.superseded_by.is_(None),
        )
        .all()
    )
    status_by_key: dict[tuple[str, str, str, str], str] = {
        (entity_type, entity_id, field, locale): status for entity_type, entity_id, field, locale, status in rows
    }

    required = 0
    present = 0
    gaps: list[TranslationGap] = []
    for key, wanted_locales in wanted.items():
        wanted_type, wanted_id, wanted_field = key
        for locale in sorted(wanted_locales):
            required += 1
            status = status_by_key.get((wanted_type, wanted_id, wanted_field, locale))
            if status == ContentVersionStatus.OK:
                present += 1
                continue
            gaps.append(
                TranslationGap(
                    entity_type=wanted_type,
                    entity_id=wanted_id,
                    field=wanted_field,
                    locale=locale,
                    reason=_REASON_BY_STATUS.get(status or "", "missing"),
                )
            )

    return TranslationCompleteness(required=required, present=present, gaps=tuple(gaps))


def promote_if_complete(db: Session, course: Course) -> bool:
    """Move a ``publishing`` course to ``published`` once it is whole.

    Called by the worker after a translation pass. Returns True when the
    course was promoted.

    Only ever moves in one direction. A course that is already
    ``published`` and has since been edited is left alone: read the rule
    literally and a typo fix would pull a live course out from under
    every student in every language until the machine caught up.
    Students keep the version that was checked, and the new text
    replaces it field by field as each one passes.
    """
    if course.status != CourseStatus.PUBLISHING:
        return False
    completeness = course_translation_completeness(db, course)
    if not completeness.is_complete:
        logger.info(
            "course %s stays in publishing: %d of %d translations ready, gaps by locale %s",
            course.id,
            completeness.present,
            completeness.required,
            completeness.by_locale(),
        )
        return False

    course.status = CourseStatus.PUBLISHED
    db.commit()
    logger.info(
        "course %s promoted to published: %d translations in place",
        course.id,
        completeness.required,
    )
    return True


__all__ = [
    "TranslationCompleteness",
    "TranslationGap",
    "course_translation_completeness",
    "promote_if_complete",
]
