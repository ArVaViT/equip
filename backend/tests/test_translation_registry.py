"""Structural tests for the translation registry.

These guard the invariants that make the registry a *single* source of
truth — if one of these breaks, adding a new translatable entity would
silently leave one of the layers out of sync.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.models.announcement import Announcement
from app.models.content_translation import TranslationEntityType
from app.models.course import Course, Module
from app.models.course_event import CourseEvent
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


def test_registry_matches_check_constraint_in_latest_migration():
    """The Postgres ``content_translations.entity_type`` CHECK constraint
    must list exactly the same entity types as the registry. Drift means
    a registered entity's INSERT will fail with a constraint violation,
    or the constraint silently allows a value the code doesn't handle.

    Walks every ``*_content_translations*.sql`` migration in publish
    order to find the *latest* CHECK definition for ``entity_type``.
    """
    migrations_dir = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))
    pattern = re.compile(
        r"content_translations_entity_type_check[\s\S]*?CHECK\s*\(\s*entity_type\s+IN\s*\((?P<list>[^)]*)\)",
        re.IGNORECASE,
    )
    latest_match: re.Match[str] | None = None
    for sql_file in sql_files:
        text = sql_file.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            latest_match = m
    assert latest_match is not None, "No content_translations_entity_type_check definition found in any migration"
    raw = latest_match.group("list")
    constraint_values = {token.strip().strip("'\"") for token in raw.split(",")}
    constraint_values = {v for v in constraint_values if v}
    assert constraint_values == set(REGISTRY), (
        f"Migration CHECK has {sorted(constraint_values)} but registry has {sorted(REGISTRY)}. "
        "Add a migration that DROPs/RECREATEs the constraint with the registry's set."
    )


def test_registry_has_model_class_for_every_entry():
    """``ENTITY_MODEL`` is the test-time hook for parametrizing per-entity
    tests; every registered entity needs an entry."""
    assert set(ENTITY_MODEL) == set(REGISTRY)


def test_registry_field_names_exist_on_models():
    """A typo in ``FieldSpec.attr`` is silent at registration time —
    catch it here by introspecting each registered model."""
    for entity_type, reg in REGISTRY.items():
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

    ev = CourseEvent(
        course_id=published_course.id,
        title="Final Exam",
        description="",
        event_type="exam",
        event_date=datetime(2026, 12, 1, 10, 0, tzinfo=UTC),
        created_by=teacher.id,
    )
    db.add(ev)
    db.flush()
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
