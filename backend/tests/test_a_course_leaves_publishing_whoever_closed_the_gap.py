# Russian is the source language of the course in these tests.
"""A course leaves ``publishing`` when it is whole — not only when the
worker happens to be the one that made it whole.

``promote_if_complete`` had one caller: the worker, after its own pass.
And the worker's pass is not the only way the last gap closes. A row
the structural check parked at ``needs_review`` is closed by a person,
through ``POST /admin/translations/accept-reviewed`` — after which no
pass runs, because the executor skips a parked row whose source is
unchanged and the sweep queues nothing for a course whose only gaps
were a person's to close. So an admin accepting the last parked row
made the course whole and nothing then looked at it. The course sat in
``publishing``, complete, invisible, for as long as nobody PATCHed it,
and the teacher's card — seeing ``is_complete`` — hid the one button
that would have kicked it.

Two exits now, and both are tested here: the admin surface promotes the
courses it completed, and the sweep promotes any whole ``publishing``
course it examines, whoever closed the gap.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Course, CourseStatus
from app.models.translation_job import TranslationJob
from app.models.user import User
from app.services.content_versions import record_human_version, record_mt_version
from app.services.translation.hash import compute_source_hash
from app.services.translation.reconciler import sweep_courses
from app.services.translation.service import reset_translation_provider_cache
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

pytestmark = pytest.mark.usefixtures("two_locales")


@pytest.fixture(autouse=True)
def _translation_enabled(monkeypatch: pytest.MonkeyPatch):
    """Without a provider the gate does not apply and every course is
    whole by definition — which would make these tests pass for the
    wrong reason."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr("test-key"), raising=False)
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def _course_in_publishing(db: Session) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", role="teacher"))
        db.commit()
    course = Course(
        id=str(uuid.uuid4()),
        created_by=TEACHER_ID,
        status=CourseStatus.PUBLISHING,
        source_locale="ru",
    )
    db.add(course)
    db.commit()
    return course


def _authored(db: Session, course: Course, field: str, text: str) -> str:
    record_human_version(db, entity_type="course", entity_id=str(course.id), field=field, locale="ru", text=text)
    db.commit()
    return compute_source_hash(text, locale="ru")


def _translated(
    db: Session,
    course: Course,
    field: str,
    source_hash: str,
    *,
    status: str = ContentVersionStatus.OK,
) -> ContentVersion:
    return record_mt_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field=field,
        locale="en",
        text=f"[en] {field}",
        source_locale="ru",
        source_hash=source_hash,
        status=status,
        review_reason="[not_translated] sample" if status == ContentVersionStatus.NEEDS_REVIEW else None,
    )


def _whole_but_for_one_parked_title(
    db: Session, *, description_translated: bool = True
) -> tuple[Course, ContentVersion]:
    course = _course_in_publishing(db)
    title_hash = _authored(db, course, "title", "Введение в Послание к Римлянам")
    description_hash = _authored(db, course, "description", "Разбор письма апостола Павла по главам.")
    if description_translated:
        _translated(db, course, "description", description_hash)
    parked = _translated(db, course, "title", title_hash, status=ContentVersionStatus.NEEDS_REVIEW)
    db.commit()
    return course, parked


class TestTheAdminSurfaceLetsTheCourseOut:
    def test_accepting_the_last_parked_row_publishes_the_course(self, admin_client: TestClient, db: Session) -> None:
        """The exact dead end from production: one parked title, an
        admin reads it and finds it fine, and the course must go out on
        that act — there is no pass coming to notice for it."""
        course, parked = _whole_but_for_one_parked_title(db)

        resp = admin_client.post("/api/v1/admin/translations/accept-reviewed", json={"ids": [str(parked.id)]})

        assert resp.status_code == 200, resp.text
        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHED

    def test_accepting_one_of_two_gaps_does_not(self, admin_client: TestClient, db: Session) -> None:
        """The gate is not weakened: a course that is still missing a
        translation stays where it is, whatever else was accepted."""
        course, parked = _whole_but_for_one_parked_title(db, description_translated=False)

        admin_client.post("/api/v1/admin/translations/accept-reviewed", json={"ids": [str(parked.id)]})

        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHING

    def test_a_published_course_is_left_where_it_is(self, admin_client: TestClient, db: Session) -> None:
        """Promotion only ever moves one way, and a course already out
        must not be touched by an accept on one of its rows."""
        course, parked = _whole_but_for_one_parked_title(db)
        course.status = CourseStatus.PUBLISHED
        db.commit()

        admin_client.post("/api/v1/admin/translations/accept-reviewed", json={"ids": [str(parked.id)]})

        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHED

    def test_retrying_a_parked_row_queues_the_course(
        self, admin_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other button. A re-opened row is ``failed``, and ``failed``
        is retried by the next pass — so there has to be a next pass,
        now, and not whenever the sweep's cycle happens to come round."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "TRANSLATION_QUEUE_ENABLED", True, raising=False)
        course, parked = _whole_but_for_one_parked_title(db)
        assert db.query(TranslationJob).filter(TranslationJob.course_id == course.id).count() == 0

        resp = admin_client.post("/api/v1/admin/translations/retry-reviewed", json={"ids": [str(parked.id)]})

        assert resp.status_code == 200, resp.text
        jobs = db.query(TranslationJob).filter(TranslationJob.course_id == course.id).all()
        assert len(jobs) == 1
        assert jobs[0].status == "queued"


class TestTheSweepLetsTheCourseOut:
    def test_a_whole_course_still_in_publishing_is_promoted(self, db: Session) -> None:
        """Whoever closed the last gap — an accept, a PATCH by hand, a
        pass on another worker — the sweep is the one thing that looks
        at every live course on a cycle, and a whole course must not
        survive its look still in ``publishing``."""
        course, parked = _whole_but_for_one_parked_title(db)
        parked.status = ContentVersionStatus.OK
        db.commit()

        report = sweep_courses(db, limit=5)

        assert report.complete == 1
        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHED

    def test_a_course_with_a_parked_row_is_not(self, db: Session) -> None:
        """Same course, gap still open: the sweep does not queue it (that
        is the older rule) and does not let it out either."""
        course, _ = _whole_but_for_one_parked_title(db)

        report = sweep_courses(db, limit=5)

        assert report.queued == 0
        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHING
