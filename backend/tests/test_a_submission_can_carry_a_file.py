"""A submission can carry a file (20261107030001).

No written work was ever handed in: the form took text, or an https:// link
to a file put somewhere else first. A sermon outline is a photo of a notebook
page or a voice memo from the phone. Now the student uploads the file into
the private ``submissions`` bucket, under their own folder for the assignment,
and hands in the key with the work.

The route trusts the key only as far as the bucket does: it must sit under
``<course>/<assignment>/<student>/`` for the caller and the assignment being
handed in, so the row the teacher opens names an object the bucket will show
them. Everything else about submitting -- the declaration, the chapter flip,
the second hand-in before marking -- is untouched by the file.
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
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

SUBMIT = "/api/v1/assignments/{}/submit"
DECLARED = {"ai_use": "none", "statement": "Без ИИ."}
COURSE = "sermon-course"


def _as_teacher(db: Session, teacher) -> TestClient:
    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: teacher
    app.dependency_overrides[get_optional_user] = lambda: teacher
    return TestClient(app, raise_server_exceptions=False)


def _assignment(db: Session, course_id: str = COURSE) -> Assignment:
    db.add(Course(id=course_id, status="published", created_by=TEACHER_ID))
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.flush()
    chapter = Chapter(
        id=f"{course_id}-a", module_id=module.id, order_index=0, chapter_type="assignment", title="Проповедь"
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.commit()
    return assignment


def _own_key(assignment: Assignment, name: str = "1762480000000-Propoved.pdf") -> str:
    return f"{COURSE}/{assignment.id}/{STUDENT_ID}/{name}"


class TestHandingInAFile:
    def test_a_file_alone_is_a_submission(self, student_client: TestClient, db: Session, teacher, student) -> None:
        """A photo of the notebook, no typed text: that is the work."""
        assignment = _assignment(db)

        resp = student_client.post(
            SUBMIT.format(assignment.id),
            json={"file": {"path": _own_key(assignment), "name": "Проповедь.pdf"}, "declaration": DECLARED},
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["file_bucket"] == "submissions"
        assert body["file_path"] == _own_key(assignment)
        assert body["file_name"] == "Проповедь.pdf"
        assert body["content"] is None
        assert body["status"] == "submitted"

    def test_text_and_a_file_together(self, student_client: TestClient, db: Session, teacher, student) -> None:
        assignment = _assignment(db)

        resp = student_client.post(
            SUBMIT.format(assignment.id),
            json={
                "content": "Конспект приложен",
                "file": {"path": _own_key(assignment, "1762480000000-konspekt.m4a"), "name": "konspekt.m4a"},
                "declaration": DECLARED,
            },
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["content"] == "Конспект приложен"
        assert resp.json()["file_name"] == "konspekt.m4a"

    def test_nothing_at_all_is_refused(self, student_client: TestClient, db: Session, teacher, student) -> None:
        """A declaration alone was once accepted as the work and marked the
        lesson done (2026-10-03). The file did not reopen that door."""
        assignment = _assignment(db)

        resp = student_client.post(SUBMIT.format(assignment.id), json={"content": "   ", "declaration": DECLARED})

        assert resp.status_code == 422, resp.text

    def test_a_submission_without_a_file_stores_none_of_the_three(
        self, student_client: TestClient, db: Session, teacher, student
    ) -> None:
        assignment = _assignment(db)

        body = student_client.post(
            SUBMIT.format(assignment.id), json={"content": "Текстом", "declaration": DECLARED}
        ).json()

        assert (body["file_bucket"], body["file_path"], body["file_name"]) == (None, None, None)


class TestTheKeyIsTheStudentsOwn:
    @pytest.mark.parametrize(
        "path",
        [
            # Another student's folder of the same assignment.
            f"{COURSE}/{{assignment}}/22222222-2222-2222-2222-222222222222/1-x.pdf",
            # Another course.
            f"other-course/{{assignment}}/{STUDENT_ID}/1-x.pdf",
            # Another assignment of the same course.
            f"{COURSE}/{uuid.uuid4()}/{STUDENT_ID}/1-x.pdf",
            # The folder itself, no file.
            f"{COURSE}/{{assignment}}/{STUDENT_ID}/",
            # The right prefix as a prefix of something else.
            f"{COURSE}/{{assignment}}/{STUDENT_ID}x/1-x.pdf",
        ],
    )
    def test_a_key_outside_the_own_folder_is_refused(
        self, student_client: TestClient, db: Session, teacher, student, path: str
    ) -> None:
        assignment = _assignment(db)

        resp = student_client.post(
            SUBMIT.format(assignment.id),
            json={"file": {"path": path.format(assignment=assignment.id), "name": "x.pdf"}, "declaration": DECLARED},
        )

        assert resp.status_code in (400, 422), resp.text
        assert student_client.get(f"/api/v1/assignments/{assignment.id}/my-submissions").json() == []

    @pytest.mark.parametrize(
        "path",
        [
            f"{COURSE}/{{assignment}}/{STUDENT_ID}/../../../etc/passwd",
            f"/{COURSE}/{{assignment}}/{STUDENT_ID}/1-x.pdf",
            f"{COURSE}/{{assignment}}/{STUDENT_ID}//1-x.pdf",
            f"{COURSE}\\{{assignment}}\\{STUDENT_ID}\\1-x.pdf",
        ],
    )
    def test_a_key_that_is_not_a_key_is_refused(
        self, student_client: TestClient, db: Session, teacher, student, path: str
    ) -> None:
        assignment = _assignment(db)

        resp = student_client.post(
            SUBMIT.format(assignment.id),
            json={"file": {"path": path.format(assignment=assignment.id), "name": "x.pdf"}, "declaration": DECLARED},
        )

        assert resp.status_code == 422, resp.text

    def test_a_name_longer_than_the_bucket_allows_is_refused(
        self, student_client: TestClient, db: Session, teacher, student
    ) -> None:
        assignment = _assignment(db)

        resp = student_client.post(
            SUBMIT.format(assignment.id),
            json={"file": {"path": _own_key(assignment), "name": "a" * 256 + ".pdf"}, "declaration": DECLARED},
        )

        assert resp.status_code == 422, resp.text

    def test_a_name_that_is_a_path_is_refused(self, student_client: TestClient, db: Session, teacher, student) -> None:
        assignment = _assignment(db)

        resp = student_client.post(
            SUBMIT.format(assignment.id),
            json={"file": {"path": _own_key(assignment), "name": "../x.pdf"}, "declaration": DECLARED},
        )

        assert resp.status_code == 422, resp.text


class TestTheTeacherSeesTheFile:
    def test_in_the_list_and_in_the_queue(self, student_client: TestClient, db: Session, teacher, student) -> None:
        assignment = _assignment(db)
        student_client.post(
            SUBMIT.format(assignment.id),
            json={"file": {"path": _own_key(assignment), "name": "Проповедь.pdf"}, "declaration": DECLARED},
        )

        client = _as_teacher(db, teacher)
        listed = client.get(f"/api/v1/assignments/{assignment.id}/submissions").json()
        queued = client.get(f"/api/v1/grades/queue/assignment/{assignment.id}").json()

        assert [(s["file_bucket"], s["file_path"], s["file_name"]) for s in listed] == [
            ("submissions", _own_key(assignment), "Проповедь.pdf")
        ]
        assert [(s["file_bucket"], s["file_path"], s["file_name"]) for s in queued] == [
            ("submissions", _own_key(assignment), "Проповедь.pdf")
        ]

    def test_the_mark_keeps_the_file(self, student_client: TestClient, db: Session, teacher, student) -> None:
        assignment = _assignment(db)
        submission_id = student_client.post(
            SUBMIT.format(assignment.id),
            json={"file": {"path": _own_key(assignment), "name": "Проповедь.pdf"}, "declaration": DECLARED},
        ).json()["id"]

        graded = _as_teacher(db, teacher).put(
            f"/api/v1/assignments/submissions/{submission_id}/grade", json={"grade": 90}
        )

        assert graded.status_code == 200, graded.text
        assert graded.json()["file_name"] == "Проповедь.pdf"
