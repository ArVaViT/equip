# ruff: noqa: RUF001
# The Russian course text is the source language in these tests; the
# English translation next to it is the point of the comparison.
"""A course enters the catalog translated, or it waits.

Publishing used to be an event: the status flipped, and translation
started afterwards inside a try/except that swallowed its own failures.
A course sat in the catalog while some of its languages were empty, and
a student who had chosen that language opened a course that did not
exist for them.

Now publication is a state the course reaches. A first publish puts the
course in ``publishing`` — invisible to students, because every reader
compares against ``published`` — and the worker promotes it when every
language has it and every translation has passed its check.

The one thing that is deliberately NOT symmetric: an already-published
course is never pulled back by an edit. Read the rule literally and a
typo fix would take a live course away from every student in every
language until the machine caught up.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Course, CourseStatus
from app.models.user import User
from app.services.content_versions import record_human_version, record_mt_version
from app.services.translation.completeness import (
    course_translation_completeness,
    promote_if_complete,
)
from app.services.translation.service import reset_translation_provider_cache
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

# The gate's mechanics are described here against the two-locale set
# they were written for; counting one target language keeps the
# assertions about the gate rather than about arithmetic. That the
# set is now four is the subject of
# ``test_german_and_ukrainian_are_served``.
pytestmark = pytest.mark.usefixtures("two_locales")


@pytest.fixture(autouse=True)
def _translation_enabled(monkeypatch: pytest.MonkeyPatch):
    """The gate only applies where translation is configured at all —
    a deploy without a Gemini key must still be able to publish."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr("test-key"), raising=False)
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


@pytest.fixture
def no_translation_in_the_request(monkeypatch: pytest.MonkeyPatch):
    """Keep the publish request from doing any translating, so the tests
    below describe the gate rather than the pipeline."""
    monkeypatch.setattr(
        "app.services.translation.pipeline_hooks.translate_course_content",
        lambda db, course: None,
    )


def _seed_teacher(db: Session) -> None:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", role="teacher"))
        db.commit()


def _make_course(db: Session, *, status: str = CourseStatus.DRAFT) -> Course:
    _seed_teacher(db)
    course = Course(
        id=str(uuid.uuid4()),
        title="Курс о Деяниях",
        description="Введение в книгу Деяний.",
        created_by=TEACHER_ID,
        status=status,
        source_locale="ru",
    )
    db.add(course)
    db.commit()
    return course


def _author(db: Session, course: Course, field: str, text: str) -> None:
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field=field,
        locale="ru",
        text=text,
    )
    db.commit()


def _translate(db: Session, course: Course, field: str, text: str, *, status=ContentVersionStatus.OK) -> None:
    record_mt_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field=field,
        locale="en",
        text=text,
        source_locale="ru",
        source_hash="hash",
        status=status,
        review_reason="[wrong_language] sample" if status == ContentVersionStatus.NEEDS_REVIEW else None,
    )
    db.commit()


class TestTheAlgorithm:
    def test_an_untranslated_course_is_incomplete(self, db: Session):
        course = _make_course(db)
        _author(db, course, "title", "Курс о Деяниях")

        completeness = course_translation_completeness(db, course)
        assert not completeness.is_complete
        assert completeness.by_locale() == {"en": completeness.required}
        assert {gap.reason for gap in completeness.gaps} == {"missing"}

    def test_a_translated_course_is_complete(self, db: Session):
        course = _make_course(db)
        _author(db, course, "title", "Курс о Деяниях")
        _author(db, course, "description", "Введение в книгу Деяний.")
        _translate(db, course, "title", "A Course on Acts")
        _translate(db, course, "description", "An introduction to the book of Acts.")

        completeness = course_translation_completeness(db, course)
        assert completeness.is_complete
        assert completeness.present == completeness.required

    def test_a_translation_awaiting_review_is_not_ready(self, db: Session):
        course = _make_course(db)
        _author(db, course, "title", "Курс о Деяниях")
        _author(db, course, "description", "Введение в книгу Деяний.")
        _translate(db, course, "title", "A Course on Acts")
        _translate(
            db,
            course,
            "description",
            "Введение в книгу Деяний.",
            status=ContentVersionStatus.NEEDS_REVIEW,
        )

        completeness = course_translation_completeness(db, course)
        assert not completeness.is_complete
        # Waiting, reading, and retrying are different work — the gap
        # says which one this is.
        assert [gap.reason for gap in completeness.gaps] == ["needs_review"]

    def test_no_provider_means_no_requirement(self, db: Session, monkeypatch: pytest.MonkeyPatch):
        # A deploy without a Gemini key would otherwise be unable to
        # publish anything at all.
        monkeypatch.setattr(
            "app.services.translation.completeness.is_translation_enabled",
            lambda: False,
        )
        course = _make_course(db)
        _author(db, course, "title", "Курс о Деяниях")

        assert course_translation_completeness(db, course).is_complete


class TestPublishing:
    def test_first_publish_waits_in_publishing(
        self,
        client: TestClient,
        db: Session,
        no_translation_in_the_request,
    ):
        course = client.post("/api/v1/courses", json={"title": "Курс о Деяниях"}).json()

        response = client.put(f"/api/v1/courses/{course['id']}", json={"status": "published"})

        assert response.status_code == 200
        assert response.json()["status"] == "publishing"

    def test_a_publishing_course_is_not_in_the_catalog(
        self,
        client: TestClient,
        db: Session,
        no_translation_in_the_request,
    ):
        course = client.post("/api/v1/courses", json={"title": "Курс о Деяниях"}).json()
        client.put(f"/api/v1/courses/{course['id']}", json={"status": "published"})

        catalog = client.get("/api/v1/courses").json()
        listed = [row["id"] for row in (catalog if isinstance(catalog, list) else catalog.get("items", []))]
        assert course["id"] not in listed


class TestPromotion:
    def test_the_worker_promotes_a_complete_course(self, db: Session):
        course = _make_course(db, status=CourseStatus.PUBLISHING)
        _author(db, course, "title", "Курс о Деяниях")
        _author(db, course, "description", "Введение в книгу Деяний.")
        _translate(db, course, "title", "A Course on Acts")
        _translate(db, course, "description", "An introduction to the book of Acts.")

        assert promote_if_complete(db, course) is True
        assert course.status == CourseStatus.PUBLISHED

    def test_an_incomplete_course_stays_where_it_is(self, db: Session):
        course = _make_course(db, status=CourseStatus.PUBLISHING)
        _author(db, course, "title", "Курс о Деяниях")

        assert promote_if_complete(db, course) is False
        assert course.status == CourseStatus.PUBLISHING

    def test_a_draft_is_never_promoted(self, db: Session):
        course = _make_course(db, status=CourseStatus.DRAFT)

        assert promote_if_complete(db, course) is False
        assert course.status == CourseStatus.DRAFT

    def test_a_published_course_is_not_pulled_back_by_an_edit(
        self,
        client: TestClient,
        db: Session,
        no_translation_in_the_request,
    ):
        # Reach ``published`` the honest way: publish, then translate,
        # then let the worker promote.
        course_id = client.post("/api/v1/courses", json={"title": "Курс о Деяниях"}).json()["id"]
        client.put(f"/api/v1/courses/{course_id}", json={"status": "published"})
        course = db.get(Course, course_id)
        assert course is not None
        for field in ("title", "description"):
            row = (
                db.query(ContentVersion)
                .filter(
                    ContentVersion.entity_type == "course",
                    ContentVersion.entity_id == course_id,
                    ContentVersion.field == field,
                    ContentVersion.locale == "ru",
                    ContentVersion.superseded_by.is_(None),
                )
                .one_or_none()
            )
            if row is not None:
                _translate(db, course, field, f"English {field}")
        promote_if_complete(db, course)
        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHED

        # Now the teacher fixes a word. The course stays live: students
        # keep the version that was checked while the new text is
        # translated behind them.
        client.put(f"/api/v1/courses/{course_id}", json={"description": "Введение в книгу Деяний, исправленное."})

        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHED
