# ruff: noqa: RUF001
"""A director teaches their own course.

On 6 September 2026 the first teacher of a real school sat down to
upload a course and could not create one. Their role was ``director``:
they run the school, and in a school this size they also teach in it.
``require_teacher`` admitted ``teacher`` and ``admin`` — the role that
opens the course-authoring surface was spelled out in the gate itself,
and the director, a role added later, was never written into it.

This file walks the director's whole day through the API, the way a
teacher's is already walked elsewhere: sign in, "my courses", a course,
a module, a chapter, a block, a quiz, publication, the gradebook, an
announcement. Then it checks the door did not swing too far: a director
still owns only what they created, and is still not platform staff.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.assignment import Assignment
from app.models.user import User, UserRole
from tests._cv_helpers import make_course_with_text
from tests.conftest import TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

_ONE_QUESTION = [
    {
        "question_text": "Is this a question?",
        "question_type": "true_false",
        "order_index": 0,
        "points": 1,
        "options": [
            {"option_text": "True", "is_correct": True, "order_index": 0},
            {"option_text": "False", "is_correct": False, "order_index": 1},
        ],
    }
]


@pytest.fixture()
def director(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="director@example.com",
        full_name="Dmytro Director",
        role=UserRole.DIRECTOR.value,
        organization_id=TEST_ORGANIZATION_ID,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def director_client(db: Session, teacher: User, director: User) -> Iterator[TestClient]:
    """Signed in as the director; the seeded teacher exists too, so there
    is a course in the same organization that is not the director's."""

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: director
    app.dependency_overrides[get_optional_user] = lambda: director
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()


def _teachers_course(db: Session, teacher: User) -> str:
    course = make_course_with_text(
        db,
        course_id="teachers-course",
        title="The Teacher's Course",
        description="Not the director's",
        status="draft",
        created_by=teacher.id,
    )
    return str(course.id)


class TestTheDirectorsDay:
    def test_the_whole_authoring_path(self, director_client: TestClient) -> None:
        # Sign in and look for the courses I teach: none yet, but the door opens.
        mine = director_client.get("/api/v1/courses/my")
        assert mine.status_code == 200, mine.text
        assert mine.json() == []

        created = director_client.post("/api/v1/courses", json={"title": "Курс о Деяниях"})
        assert created.status_code == 201, created.text
        course_id = created.json()["id"]

        mine = director_client.get("/api/v1/courses/my")
        assert [row["id"] for row in mine.json()] == [course_id]

        module = director_client.post(f"/api/v1/courses/{course_id}/modules", json={"title": "Введение"})
        assert module.status_code == 201, module.text
        module_id = module.json()["id"]

        chapter = director_client.post(
            f"/api/v1/courses/{course_id}/modules/{module_id}/chapters",
            json={"title": "Глава первая"},
        )
        assert chapter.status_code == 201, chapter.text
        chapter_id = chapter.json()["id"]

        block = director_client.post(
            f"/api/v1/blocks/chapter/{chapter_id}",
            json={"block_type": "text", "order_index": 0, "content": "В начале…"},
        )
        assert block.status_code == 201, block.text

        quiz = director_client.post(
            "/api/v1/quizzes",
            json={"chapter_id": chapter_id, "title": "Проверка", "questions": _ONE_QUESTION},
        )
        assert quiz.status_code == 201, quiz.text

        published = director_client.put(f"/api/v1/courses/{course_id}", json={"status": "published"})
        assert published.status_code == 200, published.text
        assert published.json()["status"] in ("published", "publishing")

        grades = director_client.get(f"/api/v1/grades/course/{course_id}")
        assert grades.status_code == 200, grades.text

        pending = director_client.get("/api/v1/grades/pending")
        assert pending.status_code == 200, pending.text

        announcement = director_client.post(
            "/api/v1/announcements",
            json={"title": "Начинаем", "content": "Первое занятие в понедельник.", "course_id": course_id},
        )
        assert announcement.status_code == 201, announcement.text

        readiness = director_client.get(f"/api/v1/courses/{course_id}/readiness")
        assert readiness.status_code == 200, readiness.text

        analytics = director_client.get(f"/api/v1/analytics/course/{course_id}")
        assert analytics.status_code == 200, analytics.text

    def test_editing_their_own_course(self, director_client: TestClient) -> None:
        course_id = director_client.post("/api/v1/courses", json={"title": "Черновик"}).json()["id"]
        renamed = director_client.put(f"/api/v1/courses/{course_id}", json={"title": "Курс"})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["title"] == "Курс"

    def test_reading_submissions_without_being_enrolled(self, director_client: TestClient, db: Session) -> None:
        # The one gate that did not go through ``require_teacher`` but
        # spelled the same two roles out by hand: a teacher previewing an
        # assignment is not enrolled in their own course, and neither is
        # a director.
        course_id = director_client.post("/api/v1/courses", json={"title": "Курс"}).json()["id"]
        module_id = director_client.post(f"/api/v1/courses/{course_id}/modules", json={"title": "М"}).json()["id"]
        chapter_id = director_client.post(
            f"/api/v1/courses/{course_id}/modules/{module_id}/chapters", json={"title": "Г"}
        ).json()["id"]
        assignment = Assignment(chapter_id=chapter_id)
        db.add(assignment)
        db.commit()

        resp = director_client.get(f"/api/v1/assignments/{assignment.id}/my-submissions")
        assert resp.status_code == 200, resp.text


class TestTheDoorDidNotSwingTooFar:
    """Opening the surface to the role must not open anyone else's course."""

    def test_a_teachers_course_in_the_same_organization(
        self, director_client: TestClient, db: Session, teacher: User
    ) -> None:
        course_id = _teachers_course(db, teacher)

        assert director_client.put(f"/api/v1/courses/{course_id}", json={"title": "Моё"}).status_code == 403
        assert director_client.delete(f"/api/v1/courses/{course_id}").status_code == 403
        assert (
            director_client.post(f"/api/v1/courses/{course_id}/modules", json={"title": "Чужой модуль"}).status_code
            == 403
        )
        assert director_client.get(f"/api/v1/grades/course/{course_id}").status_code == 403
        assert (
            director_client.post(
                "/api/v1/announcements",
                json={"title": "Не моё", "content": "…", "course_id": course_id},
            ).status_code
            == 403
        )
        # And it is not in "my courses" either: ownership, not organization.
        mine = director_client.get("/api/v1/courses/my")
        assert course_id not in [row["id"] for row in mine.json()]

    def test_a_director_is_still_not_platform_staff(self, director_client: TestClient) -> None:
        # Site-wide announcements and the audit log belong to Equip, not
        # to any one school; a director gets the same answer a teacher does.
        broadcast = director_client.post("/api/v1/announcements", json={"title": "Всем", "content": "…"})
        assert broadcast.status_code == 403, broadcast.text
        assert director_client.get("/api/v1/audit").status_code == 403

    def test_a_student_is_still_refused(self, student_client: TestClient) -> None:
        assert student_client.get("/api/v1/courses/my").status_code == 403
        assert student_client.post("/api/v1/courses", json={"title": "Нет"}).status_code == 403
