"""Regression tests for the fire-and-forget translation hooks.

The hooks have one job: never propagate an error to the caller and
never leave the SQLAlchemy session in a broken state, no matter what
the orchestrator or provider does.

There are two delivery modes behind ``settings.TRANSLATION_QUEUE_ENABLED``.
In queue mode — the default, and what production runs — the publish hook
enqueues a job for the cron-driven worker instead of calling
``translate_course_content`` inside the request. Both modes are tested,
and the tests that mean the synchronous one say so.
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session  # noqa: TC002 — pytest needs runtime types

from app.models.announcement import Announcement
from app.models.course import Course
from app.models.translation_job import TranslationJob, TranslationJobStatus
from app.services.translation.pipeline_hooks import (
    reconcile_entity_if_course_published,
    run_course_translation_pipeline_if_published,
)
from app.services.translation.protocol import TranslationError


def _seed_published_course(db: Session, teacher_id, *, status: str = "published") -> Course:
    course = Course(
        id=f"hook-{uuid.uuid4().hex[:8]}",
        status=status,
        source_locale="ru",
        created_by=teacher_id,
    )
    db.add(course)
    db.commit()
    return course


def test_course_pipeline_swallows_translation_error_at_info(db: Session, teacher, caplog, monkeypatch):
    # This test exercises the synchronous path, which is no longer the
    # default. Pin the flag rather than relying on the setting.
    monkeypatch.setattr("app.core.config.settings.TRANSLATION_QUEUE_ENABLED", False)
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


def test_course_pipeline_swallows_unexpected_error_at_error(db: Session, teacher, caplog, monkeypatch):
    # This test exercises the synchronous path, which is no longer the
    # default. Pin the flag rather than relying on the setting.
    monkeypatch.setattr("app.core.config.settings.TRANSLATION_QUEUE_ENABLED", False)
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


def test_course_pipeline_rolls_back_on_sqlalchemy_error(db: Session, teacher, caplog, monkeypatch):
    """A SQLAlchemyError leaves the session in a broken state until
    rollback. The hook MUST roll back so the request's next query does
    not inherit a poisoned transaction."""
    # This test exercises the synchronous path, which is no longer the
    # default. Pin the flag rather than relying on the setting.
    monkeypatch.setattr("app.core.config.settings.TRANSLATION_QUEUE_ENABLED", False)
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
    # ``publishing`` rather than ``published``: on a live course an edit
    # is held for its translations and goes down the staged path
    # instead, which has its own suppression test below. This one is
    # about ``reconcile_entity``, which is what a course on its way out
    # still uses.
    course = _seed_published_course(db, teacher.id, status="publishing")
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
    course = _seed_published_course(db, teacher.id, status="publishing")
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
    course = _seed_published_course(db, teacher.id, status="publishing")
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


def test_staged_edit_path_swallows_its_failures_too(db: Session, teacher, caplog):
    """The rule the hooks exist for holds on the new path as well: a
    teacher's save must survive the pipeline failing.

    It matters more here, not less. The edit is already recorded in the
    staging table by the time this runs, so a failure means the
    translation is late — the next worker tick picks it up — whereas a
    raised exception would mean the save itself came back an error for
    work that had in fact succeeded."""
    course = _seed_published_course(db, teacher.id)
    ann = Announcement(course_id=course.id, created_by=teacher.id)
    db.add(ann)
    db.flush()
    with (
        patch(
            "app.services.translation.staged_pipeline.translate_staged_edits",
            side_effect=TranslationError("gemini exploded"),
        ),
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
        patch("app.core.config.settings.TRANSLATION_QUEUE_ENABLED", False),
        caplog.at_level(logging.INFO, logger="app.services.translation.pipeline_hooks"),
    ):
        reconcile_entity_if_course_published(db, "announcement", ann)

    records = [r for r in caplog.records if r.name == "app.services.translation.pipeline_hooks"]
    assert records, "expected the failure to be logged rather than raised"
    assert records[-1].scope == "staged-edit"


def test_a_live_course_enqueues_rather_than_translating_in_the_request(db: Session, teacher):
    """With the queue on, an edit to a live course costs the teacher one
    INSERT. The Gemini round trips — one per language, per field —
    happen on the worker, not inside their save."""
    course = _seed_published_course(db, teacher.id)
    ann = Announcement(course_id=course.id, created_by=teacher.id)
    db.add(ann)
    db.flush()
    with (
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
        patch("app.core.config.settings.TRANSLATION_QUEUE_ENABLED", True),
        patch("app.services.translation.staged_pipeline.translate_staged_edits") as translate,
    ):
        reconcile_entity_if_course_published(db, "announcement", ann)

    translate.assert_not_called()
    jobs = db.query(TranslationJob).filter(TranslationJob.course_id == course.id).all()
    assert [j.status for j in jobs] == [TranslationJobStatus.QUEUED]


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


# ---------------------------------------------------------------------------
# queue-mode publish path
# ---------------------------------------------------------------------------


def test_queue_mode_enqueues_job_instead_of_calling_orchestrator(db: Session, teacher, monkeypatch):
    """When TRANSLATION_QUEUE_ENABLED=True the hook MUST NOT call the
    sync orchestrator. It enqueues one job and returns; the worker
    cron drains it out-of-band."""
    monkeypatch.setattr(
        "app.services.translation.pipeline_hooks.settings.TRANSLATION_QUEUE_ENABLED",
        True,
        raising=False,
    )
    course = _seed_published_course(db, teacher.id)
    with (
        patch("app.services.translation.pipeline_hooks.translate_course_content") as orchestrator,
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
    ):
        run_course_translation_pipeline_if_published(db, course.id)
    orchestrator.assert_not_called()

    queued = db.query(TranslationJob).filter_by(course_id=course.id).all()
    assert len(queued) == 1
    assert queued[0].status == TranslationJobStatus.QUEUED


def test_queue_mode_is_idempotent_on_repeated_saves(db: Session, teacher, monkeypatch):
    """A teacher mashing Save five times in a row must enqueue exactly
    one pending job — the enqueue helper short-circuits on existing
    queued/processing rows."""
    monkeypatch.setattr(
        "app.services.translation.pipeline_hooks.settings.TRANSLATION_QUEUE_ENABLED",
        True,
        raising=False,
    )
    course = _seed_published_course(db, teacher.id)
    with patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True):
        for _ in range(5):
            run_course_translation_pipeline_if_published(db, course.id)

    queued = db.query(TranslationJob).filter_by(course_id=course.id).all()
    assert len(queued) == 1


def test_queue_mode_no_op_on_draft_course(db: Session, teacher, monkeypatch):
    """Draft course publish-hook fires during course building — must
    not enqueue (no work to do) and must not blow up."""
    monkeypatch.setattr(
        "app.services.translation.pipeline_hooks.settings.TRANSLATION_QUEUE_ENABLED",
        True,
        raising=False,
    )
    course = Course(
        id=f"hook-draft-{uuid.uuid4().hex[:8]}",
        status="draft",
        source_locale="ru",
        created_by=teacher.id,
    )
    db.add(course)
    db.commit()
    with patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True):
        run_course_translation_pipeline_if_published(db, course.id)
    queued = db.query(TranslationJob).filter_by(course_id=course.id).count()
    assert queued == 0


def test_sync_mode_still_works_when_flag_is_off(db: Session, teacher, monkeypatch):
    """The legacy sync path is the deploy-time default until the cron
    worker is verified running. Make sure flipping the flag off keeps
    the orchestrator wired."""
    monkeypatch.setattr(
        "app.services.translation.pipeline_hooks.settings.TRANSLATION_QUEUE_ENABLED",
        False,
        raising=False,
    )
    course = _seed_published_course(db, teacher.id)
    with (
        patch("app.services.translation.pipeline_hooks.translate_course_content") as orchestrator,
        patch("app.services.translation.pipeline_hooks.is_translation_enabled", return_value=True),
    ):
        run_course_translation_pipeline_if_published(db, course.id)
    orchestrator.assert_called_once()

    queued = db.query(TranslationJob).filter_by(course_id=course.id).count()
    assert queued == 0
