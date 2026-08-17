"""Reading the staging table: what is in flight, and how far along.

Three questions, three callers:

* **The pipeline** asks what still needs translating, and gets field
  specs it can hand to the orchestrator unchanged.
* **The promotion sweep** asks which fields are whole.
* **The teacher** asks why their edit has not appeared yet, and
  deserves a better answer than silence — including the case where it
  never will appear on its own, because a translation failed its check
  and a person has to look.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.staged_content_version import StagedContentVersion
from app.schemas.locale import LOCALE_CODES

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course

StagedFieldState = Literal["translating", "ready", "blocked"]


@dataclass(frozen=True, slots=True)
class StagedFieldStatus:
    """One field's edit, and what is standing between it and readers."""

    entity_type: str
    entity_id: str
    field: str
    source_locale: str
    state: StagedFieldState
    #: Locales that still have no ``ok`` staged translation.
    pending_locales: tuple[str, ...]
    #: Locales whose translation came back and failed its check, or
    #: exhausted its retries. These do not resolve on their own.
    blocked_locales: tuple[str, ...]


def staged_human_rows(db: Session, course_id: str) -> list[StagedContentVersion]:
    """Every held edit for this course — the source rows, not their
    translations."""
    return (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.course_id == course_id,
            StagedContentVersion.origin == "human",
        )
        .order_by(StagedContentVersion.created_at)
        .all()
    )


def staged_translation_rows(db: Session, course_id: str) -> list[StagedContentVersion]:
    return (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.course_id == course_id,
            StagedContentVersion.origin == "mt",
        )
        .all()
    )


def staged_field_specs(db: Session, course_id: str) -> list[tuple[str, str, str, str, str]]:
    """``(entity_type, entity_id, field, source_locale, text)`` per held edit.

    The pipeline turns each of these into one orchestrator call. The
    source locale is the language the edit was written in — recorded at
    staging time by the same per-field detector the live path uses, so
    a German paragraph edited inside a Russian course still translates
    outward from German.
    """
    return [
        (row.entity_type, row.entity_id, row.field, row.locale, row.text) for row in staged_human_rows(db, course_id)
    ]


def _human_translation_locales(
    db: Session,
    keys: set[tuple[str, str, str]],
) -> dict[tuple[str, str, str], set[str]]:
    """Locales where a person — not the machine — wrote the translation.

    Those rows are never regenerated (the pipeline refuses to overwrite
    human text), so waiting for a fresh machine translation of them
    would wait forever. They count as satisfied: the hand-written
    translation stays, and the field can go out. It is the one place
    where an edit lands with one language's wording predating it, and
    the alternative — a field frozen until somebody re-translates by
    hand — serves nobody.
    """
    if not keys:
        return {}
    rows = (
        db.query(
            ContentVersion.entity_type,
            ContentVersion.entity_id,
            ContentVersion.field,
            ContentVersion.locale,
        )
        .filter(
            ContentVersion.superseded_by.is_(None),
            ContentVersion.origin == "human",
            ContentVersion.status == ContentVersionStatus.OK,
            ContentVersion.entity_id.in_({eid for _, eid, _ in keys}),
        )
        .all()
    )
    out: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for entity_type, entity_id, field, locale in rows:
        key = (entity_type, entity_id, field)
        if key in keys:
            out[key].add(locale)
    return dict(out)


def staged_status_for_course(db: Session, course: Course) -> list[StagedFieldStatus]:
    """Every in-flight edit for this course, with what it is waiting on.

    ``ready`` means promotion will take it on its next pass.
    ``translating`` means the machine still has work to do.
    ``blocked`` means it will not resolve without a person: a
    translation failed its structural check, or ran out of retries.
    That last state is the one worth surfacing loudly — an edit in it
    is invisible to students indefinitely, and silence would read to
    the teacher as "my change did nothing".
    """
    humans = staged_human_rows(db, str(course.id))
    if not humans:
        return []

    staged_by_key: dict[tuple[str, str, str], dict[str, StagedContentVersion]] = defaultdict(dict)
    for row in staged_translation_rows(db, str(course.id)):
        staged_by_key[(row.entity_type, row.entity_id, row.field)][row.locale] = row

    keys = {(h.entity_type, h.entity_id, h.field) for h in humans}
    hand_translated = _human_translation_locales(db, keys)

    out: list[StagedFieldStatus] = []
    for human in humans:
        key = (human.entity_type, human.entity_id, human.field)
        translations = staged_by_key.get(key, {})
        exempt = hand_translated.get(key, set())
        pending: list[str] = []
        blocked: list[str] = []
        for locale in LOCALE_CODES:
            if locale == human.locale or locale in exempt:
                continue
            staged_row = translations.get(locale)
            if staged_row is None:
                pending.append(locale)
            elif staged_row.status == ContentVersionStatus.OK:
                continue
            elif staged_row.status in (
                ContentVersionStatus.NEEDS_REVIEW,
                ContentVersionStatus.FAILED_PERMANENT,
            ):
                blocked.append(locale)
            else:
                pending.append(locale)

        state: StagedFieldState = "ready" if not pending and not blocked else ("blocked" if blocked else "translating")
        out.append(
            StagedFieldStatus(
                entity_type=human.entity_type,
                entity_id=human.entity_id,
                field=human.field,
                source_locale=human.locale,
                state=state,
                pending_locales=tuple(pending),
                blocked_locales=tuple(blocked),
            )
        )
    return out


def author_text(db: Session, *, entity_type: str, entity_id: str, field: str) -> str | None:
    """The author's own unreleased text for one field, if there is one.

    Every surface that answers a teacher about their own content goes
    through here — the response to a save, the editor's ``?source=1``
    view, the list of blocks in the course builder. Without it, a
    teacher saves an edit, gets the previous text back in the response,
    and reasonably concludes the save failed. They then retype it, and
    the second save is identical to the first, which the pipeline
    correctly recognises as no change at all.

    Readers never call this. That is the whole distinction: the person
    who wrote the words sees the words they wrote; everyone else sees
    what has been released in their language.
    """
    return (
        db.query(StagedContentVersion.text)
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id == entity_id,
            StagedContentVersion.field == field,
            StagedContentVersion.origin == "human",
        )
        .scalar()
    )


def author_texts_bulk(
    db: Session,
    *,
    entity_type: str,
    entity_ids: list[str],
    fields: list[str],
) -> dict[tuple[str, str], str]:
    """Bulk form of ``author_text``, keyed ``(entity_id, field)``.

    One query for a whole list — the course builder renders dozens of
    blocks, and a per-row lookup there would be an N+1 on every page
    load of the editor.
    """
    if not entity_ids or not fields:
        return {}
    rows = (
        db.query(
            StagedContentVersion.entity_id,
            StagedContentVersion.field,
            StagedContentVersion.text,
        )
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id.in_(entity_ids),
            StagedContentVersion.field.in_(fields),
            StagedContentVersion.origin == "human",
        )
        .all()
    )
    return {(entity_id, field): text for entity_id, field, text in rows}


def staged_texts_for_entity(
    db: Session,
    *,
    entity_type: str,
    entity_ids: list[str],
    fields: list[str],
    locale: str,
) -> dict[tuple[str, str], str]:
    """The teacher's own unreleased text, for the editing surface.

    Readers must never see this. The person who wrote it must never
    see anything else: an editor that shows the old text back after a
    successful save reads as a lost edit, and the teacher retypes it.
    Keyed ``(entity_id, field)`` to drop straight into the same overlay
    dicts the live path builds.
    """
    if not entity_ids or not fields:
        return {}
    rows = (
        db.query(
            StagedContentVersion.entity_id,
            StagedContentVersion.field,
            StagedContentVersion.text,
        )
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id.in_(entity_ids),
            StagedContentVersion.field.in_(fields),
            StagedContentVersion.locale == locale,
            StagedContentVersion.status == ContentVersionStatus.OK,
        )
        .all()
    )
    return {(entity_id, field): text for entity_id, field, text in rows}


__all__ = [
    "StagedFieldStatus",
    "author_text",
    "author_texts_bulk",
    "staged_field_specs",
    "staged_human_rows",
    "staged_status_for_course",
    "staged_texts_for_entity",
    "staged_translation_rows",
]
