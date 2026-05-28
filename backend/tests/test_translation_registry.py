"""Structural tests for the translation registry.

These guard the invariants that make the registry a *single* source of
truth — if one of these breaks, adding a new translatable entity would
silently leave one of the layers out of sync.
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

import pytest

from app.models.announcement import Announcement
from app.models.content_version import ContentVersionEntityType as TranslationEntityType
from app.models.course import Course, Module
from app.services.translation.protocol import EntityType
from app.services.translation.registry import (
    ENTITY_MODEL,
    REGISTRY,
    reconcile_entity,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Cross-layer consistency
# ---------------------------------------------------------------------------


def test_registry_keys_match_pydantic_literal():
    """Adding a new entity must update both ``REGISTRY`` and the
    ``EntityType`` ``Literal`` in ``protocol.py`` (the type the
    orchestrator uses to type-check ``translate_entity_fields`` callers)."""
    assert set(REGISTRY) == set(typing.get_args(EntityType))


def test_registry_keys_match_model_literal():
    """The model-side ``TranslationEntityType`` Literal must also stay
    in lockstep — drift here means SQLAlchemy will accept inserts the
    Pydantic schema doesn't, and vice versa."""
    assert set(REGISTRY) == set(typing.get_args(TranslationEntityType))


# Phase 5d removed the ``content_translations.entity_type`` CHECK
# constraint test — the table itself is dropped. ``content_versions``
# deliberately has no CHECK on ``entity_type`` (so a new entity type
# is INSERT, not DDL); registry vs cv parity is enforced at the API
# edge by the ``ContentVersionEntityType`` Literal, asserted in
# ``test_registry_keys_match_model_literal`` above.


def test_registry_has_model_class_for_every_entry():
    """``ENTITY_MODEL`` is the test-time hook for parametrizing per-entity
    tests; every registered entity needs an entry."""
    assert set(ENTITY_MODEL) == set(REGISTRY)


def test_registry_field_names_exist_on_models():
    """A typo in ``FieldSpec.attr`` is silent at registration time —
    catch it here by introspecting each registered model.

    Phase 5e1: ``cohort`` is exempt — its source column (``name``) was
    dropped; the cohort's display text lives only in ``content_versions``
    and the dual-write path in ``api/v1/cohorts.py`` reads from cv.
    Phase 5e2: ``chapter_block`` is exempt for the same reason — its
    ``content`` column was dropped and the block routes pass an explicit
    ``texts={"content": ...}`` dict to ``dual_write_entity_content``.
    The MT pipeline's ``reconcile_entity`` still iterates each entity's
    FieldSpec but ``getattr(entity, attr, None)`` returns None, so it
    cleanly no-ops for cv-only entities.
    """
    cv_only_entities = {"cohort", "chapter_block", "assignment", "course_event"}
    for entity_type, reg in REGISTRY.items():
        if entity_type in cv_only_entities:
            continue
        model = ENTITY_MODEL[entity_type]
        attrs = set(dir(model))
        for fs in reg.fields:
            assert fs.attr in attrs, (
                f"Registry says {entity_type!r} reads field {fs.attr!r}, but {model.__name__} has no such attribute"
            )


# ---------------------------------------------------------------------------
# reconcile_entity behavior (lightweight, the orchestrator path is covered
# elsewhere — these tests only check the new wiring).
# ---------------------------------------------------------------------------


@pytest.fixture
def published_course(db: Session, teacher) -> Course:
    course = Course(
        id="test-registry-course",
        title="Registry Test Course",
        description="A test course for registry behavior tests.",
        status="published",
        source_locale="ru",
        created_by=teacher.id,
    )
    db.add(course)
    db.flush()
    return course


def test_reconcile_orphan_announcement_is_noop(db: Session, teacher):
    """An announcement with no ``course_id`` has no source locale to
    translate from. Should silently no-op, not raise."""
    ann = Announcement(title="Orphan", content="No course", course_id=None, created_by=teacher.id)
    db.add(ann)
    db.flush()
    report = reconcile_entity(db, "announcement", ann)
    assert (report.translated, report.skipped, report.failed) == (0, 0, 0)


def test_reconcile_event_with_empty_description_skips_that_field(
    db: Session,
    teacher,
    published_course: Course,
):
    """An entity with one empty translatable field should still
    reconcile the non-empty fields, not skip the whole entity."""
    from datetime import UTC, datetime

    # Phase 5e4: title + description columns dropped; reconcile pulls
    # from cv now. Use the helper to seed the source rows.
    from ._cv_helpers import make_course_event_with_text

    ev = make_course_event_with_text(
        db,
        course_id=published_course.id,
        title="Final Exam",
        description="",
        event_type="exam",
        event_date=datetime(2026, 12, 1, 10, 0, tzinfo=UTC),
        created_by=teacher.id,
    )
    report = reconcile_entity(db, "course_event", ev)
    assert report.failed == 0


def test_reconcile_module_resolves_course_via_attr(
    db: Session,
    published_course: Course,
):
    """Module spec uses ``course_id`` attribute resolver — verify the
    indirection actually finds the course."""
    m = Module(
        id="test-registry-module",
        course_id=published_course.id,
        title="Module One",
        description="A test module description.",
        order_index=1,
    )
    db.add(m)
    db.flush()
    report = reconcile_entity(db, "module", m)
    assert report.failed == 0


def test_reconcile_with_no_provider_returns_empty_when_disabled(
    db: Session,
    published_course: Course,
    monkeypatch: pytest.MonkeyPatch,
):
    """When ``GEMINI_API_KEY`` is unset (test default), reconcile is a
    no-op — protects teacher saves from MT outage."""
    monkeypatch.setattr("app.services.translation.registry.is_translation_enabled", lambda: False)
    report = reconcile_entity(db, "course", published_course)
    assert (report.translated, report.skipped, report.failed) == (0, 0, 0)
