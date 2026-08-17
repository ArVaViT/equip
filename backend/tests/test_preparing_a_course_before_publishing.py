# ruff: noqa: RUF001
# Russian test content on purpose: the course being prepared is written in
# one language and served in four, which is the situation these endpoints
# exist for. A Latin stand-in would not exercise the same path.
"""Getting a course translated before it goes out, and knowing where it is.

A draft is not translated by the pipeline: nobody is reading it, and
paying to translate wording that is still being rewritten is money spent
on sentences that will not survive the week. The consequence is that all
of the work lands at the moment of publication, and a large course sits
in ``publishing`` — invisible to everyone — for as long as that takes.

So the teacher gets to say when. "Prepare for publication" runs the
pipeline ahead of time; by the time they press publish there is nothing
left to do and the course goes out at once.

The second half is being able to see it happen. A progress call that
disagreed with the publication gate would be worse than none — the
button would say ready and the gate would refuse — so both read the same
completeness.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr

from app.models.course import Course
from app.models.staged_content_version import StagedContentVersion
from app.models.translation_job import TranslationJob, TranslationJobStatus
from app.models.user import User
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.translation.hash import compute_source_hash
from app.services.translation.service import reset_translation_provider_cache
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

_PREFIX = "/api/v1/courses"


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


def _course(db: Session, **overrides: Any) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"prep-{uuid.uuid4().hex[:8]}",
        status=overrides.pop("status", "draft"),
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="ru",
        text="Курс о Деяниях",
    )
    db.commit()
    return course


def test_preparing_a_draft_hands_the_work_to_the_worker(client: TestClient, db: Session, monkeypatch):
    """Not done inside the request. A course is hundreds of provider round
    trips, and a request that waits for them ends in 504 with the work
    half finished and no way for the caller to know."""
    monkeypatch.setattr("app.core.config.settings.TRANSLATION_QUEUE_ENABLED", True)
    course = _course(db)

    resp = client.post(f"{_PREFIX}/{course.id}/translate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["queued"] is True
    assert body["enabled"] is True

    jobs = db.query(TranslationJob).filter(TranslationJob.course_id == course.id).all()
    assert [j.status for j in jobs] == [TranslationJobStatus.QUEUED]


def test_a_second_press_does_not_queue_the_work_twice(client: TestClient, db: Session, monkeypatch):
    """A teacher who presses twice should not pay Gemini twice."""
    monkeypatch.setattr("app.core.config.settings.TRANSLATION_QUEUE_ENABLED", True)
    course = _course(db)

    client.post(f"{_PREFIX}/{course.id}/translate")
    client.post(f"{_PREFIX}/{course.id}/translate")

    assert db.query(TranslationJob).filter(TranslationJob.course_id == course.id).count() == 1


def test_progress_reports_what_is_still_missing_and_in_which_language(client: TestClient, db: Session):
    """One number would hide the thing that matters: which audience is
    waiting. A course that is complete in three languages and empty in
    the fourth is not 75% ready — it is not ready for Germans."""
    course = _course(db)
    # Title exists in ru (the source) and en only.
    record_mt_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="en",
        text="A course on Acts",
        source_locale="ru",
        source_hash=compute_source_hash("Курс о Деяниях", locale="ru"),
    )
    db.commit()

    resp = client.get(f"{_PREFIX}/{course.id}/translation-progress")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is False
    assert body["present"] == 1
    assert body["required"] == 3  # en, de, uk
    assert body["by_locale"] == {"de": 1, "uk": 1}
    assert body["gaps"]["missing"] == 2


def test_progress_agrees_with_the_publication_gate(client: TestClient, db: Session):
    """The button and the gate read the same completeness. If they could
    disagree, the button would say ready and publishing would refuse."""
    course = _course(db)
    source_hash = compute_source_hash("Курс о Деяниях", locale="ru")
    for locale in ("en", "de", "uk"):
        record_mt_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale=locale,
            text=f"[{locale}] Acts",
            source_locale="ru",
            source_hash=source_hash,
        )
    db.commit()

    progress = client.get(f"{_PREFIX}/{course.id}/translation-progress").json()
    assert progress["is_complete"] is True

    published = client.put(f"{_PREFIX}/{course.id}", json={"status": "published"})
    assert published.status_code == 200
    # Complete, so it goes straight out rather than waiting in ``publishing``.
    assert published.json()["status"] == "published"


def test_progress_surfaces_edits_that_are_stuck(client: TestClient, db: Session):
    """A held edit whose translation failed its check does not resolve on
    its own. Reporting it is the difference between "my change is on its
    way" and "my change did nothing", which is what the teacher would
    otherwise conclude."""
    course = _course(db, status="published")
    db.add(
        StagedContentVersion(
            entity_type="course",
            entity_id=str(course.id),
            course_id=str(course.id),
            field="title",
            locale="ru",
            text="Исправленное название",
            origin="human",
            status="ok",
        )
    )
    db.add(
        StagedContentVersion(
            entity_type="course",
            entity_id=str(course.id),
            course_id=str(course.id),
            field="title",
            locale="de",
            text="Etwas, das die Prüfung nicht bestand",
            origin="mt",
            status="needs_review",
            review_reason="[markup_mismatch]",
            source_locale="ru",
            source_hash=compute_source_hash("Исправленное название", locale="ru"),
        )
    )
    db.commit()

    body = client.get(f"{_PREFIX}/{course.id}/translation-progress").json()

    assert body["held_edits"] == 1
    assert body["blocked_edits"] == 1


def test_progress_is_owner_only(student_client: TestClient, db: Session):
    """Same rule as the rest of the course-edit surface: a stranger does
    not get to see which parts of an unpublished course exist."""
    course = _course(db)

    resp = student_client.get(f"{_PREFIX}/{course.id}/translation-progress")

    assert resp.status_code in (403, 404)
