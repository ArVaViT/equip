"""Regression tests for the fire-and-forget translation hooks.

The hooks have one job: never propagate an error to the caller and
never leave the SQLAlchemy session in a broken state, no matter what
the orchestrator or provider does.
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session  # noqa: TC002 — pytest needs runtime types

from app.models.announcement import Announcement
from app.models.course import Course
from app.services.translation.pipeline_hooks import (
    reconcile_entity_if_course_published,
    run_course_translation_pipeline_if_published,
)
from app.services.translation.protocol import TranslationError


def _seed_published_course(db: Session, teacher_id) -> Course:
    course = Course(
        id=f"hook-{uuid.uuid4().hex[:8]}",
        status="published",
        source_locale="ru",
        created_by=teacher_id,
    )
    db.add(course)
    db.commit()
    return course


def test_course_pipeline_swallows_translation_error_at_info(db: Session, teacher, caplog):
    course = _seed_published_course(db, teacher.id)
    with (
        patch(
            "app.services.translation.pipeline_hooks.translate_course_content",
            side_effect=TranslationError("gemini exploded"),
        ),
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
        caplog.at_level(logging.INFO, logger="app.services.translation.pipeline_hooks"),
    ):
        run_course_translation_pipeline_if_published(db, course.id)

    records = [r for r in caplog.records if r.name == "app.services.translation.pipeline_hooks"]
    assert records, "expected at least one log record from the hook"
    rec = records[-1]
    assert rec.levelno == logging.INFO
    assert rec.failure_class == "TranslationError"
    assert rec.scope == "course-pipeline"
    assert rec.entity_type == "course"
    assert rec.entity_id == course.id


def test_course_pipeline_swallows_unexpected_error_at_error(db: Session, teacher, caplog):
    course = _seed_published_course(db, teacher.id)
    with (
        patch(
            "app.services.translation.pipeline_hooks.translate_course_content",
            side_effect=RuntimeError("not our day"),
        ),
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
        caplog.at_level(logging.INFO, logger="app.services.translation.pipeline_hooks"),
    ):
        run_course_translation_pipeline_if_published(db, course.id)

    records = [r for r in caplog.records if r.name == "app.services.translation.pipeline_hooks"]
    rec = records[-1]
    assert rec.levelno == logging.ERROR
    assert rec.failure_class == "RuntimeError"
    assert rec.exc_info is not None


def test_course_pipeline_rolls_back_on_sqlalchemy_error(db: Session, teacher, caplog):
    """A SQLAlchemyError leaves the session in a broken state until
    rollback. The hook MUST roll back so the request's next query does
    not inherit a poisoned transaction."""
    course = _seed_published_course(db, teacher.id)
    with (
        patch(
            "app.services.translation.pipeline_hooks.translate_course_content",
            side_effect=OperationalError("stmt", {}, BaseException("db unreachable")),
        ),
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
        patch.object(db, "rollback") as rollback,
        caplog.at_level(logging.ERROR, logger="app.services.translation.pipeline_hooks"),
    ):
        run_course_translation_pipeline_if_published(db, course.id)

    rollback.assert_called_once()


def test_entity_reconcile_swallows_translation_error(db: Session, teacher, caplog):
    course = _seed_published_course(db, teacher.id)
    ann = Announcement(course_id=course.id, created_by=teacher.id)
    db.add(ann)
    db.flush()
    with (
        patch(
            "app.services.translation.pipeline_hooks.reconcile_entity",
            side_effect=TranslationError("gemini exploded"),
        ),
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
        caplog.at_level(logging.INFO, logger="app.services.translation.pipeline_hooks"),
    ):
        reconcile_entity_if_course_published(db, "announcement", ann)

    records = [r for r in caplog.records if r.name == "app.services.translation.pipeline_hooks"]
    rec = records[-1]
    assert rec.levelno == logging.INFO
    assert rec.failure_class == "TranslationError"
    assert rec.scope == "entity-reconcile"
    assert rec.entity_type == "announcement"


def test_entity_reconcile_swallows_unexpected_error_with_traceback(db: Session, teacher, caplog):
    course = _seed_published_course(db, teacher.id)
    ann = Announcement(course_id=course.id, created_by=teacher.id)
    db.add(ann)
    db.flush()
    with (
        patch(
            "app.services.translation.pipeline_hooks.reconcile_entity",
            side_effect=AttributeError("course.title"),
        ),
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
        caplog.at_level(logging.ERROR, logger="app.services.translation.pipeline_hooks"),
    ):
        reconcile_entity_if_course_published(db, "announcement", ann)

    records = [r for r in caplog.records if r.name == "app.services.translation.pipeline_hooks"]
    rec = records[-1]
    assert rec.levelno == logging.ERROR
    assert rec.failure_class == "AttributeError"
    assert rec.exc_info is not None


def test_entity_reconcile_rolls_back_on_sqlalchemy_error(db: Session, teacher):
    course = _seed_published_course(db, teacher.id)
    ann = Announcement(course_id=course.id, created_by=teacher.id)
    db.add(ann)
    db.flush()
    with (
        patch(
            "app.services.translation.pipeline_hooks.reconcile_entity",
            side_effect=OperationalError("stmt", {}, BaseException("db gone")),
        ),
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
        patch.object(db, "rollback") as rollback,
    ):
        reconcile_entity_if_course_published(db, "announcement", ann)

    rollback.assert_called_once()


def test_course_pipeline_skips_draft(db: Session, teacher):
    """The hooks check status before doing anything — saves on draft
    courses must never call the orchestrator."""
    course = Course(
        id=f"hook-draft-{uuid.uuid4().hex[:8]}",
        status="draft",
        source_locale="ru",
        created_by=teacher.id,
    )
    db.add(course)
    db.commit()
    with (
        patch("app.services.translation.pipeline_hooks.translate_course_content") as translate,
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
    ):
        run_course_translation_pipeline_if_published(db, course.id)
    translate.assert_not_called()
