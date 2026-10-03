"""Work handed in after the deadline is accepted and marked as late (2026-10-03).

Assignments carried a ``due_date`` that was set, shown on the student's page
and never consulted when the work arrived: a submission a week after the
deadline looked, to the teacher, exactly like one a week before it. Refusing
late work is not the answer — a Bible school's deadlines are pastoral, and
the teacher decides what a late essay costs. The platform's job is to make
sure the teacher *knows*.

So nothing is refused. Every submission response — the student's, the
teacher's list, the marking queue — carries ``is_late``, computed from the
moment the work arrived against the deadline, both as UTC instants. The same
flag sits on a quiz attempt, read against its module's due date, which was
the only deadline a quiz ever had.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.assignment import Assignment
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizQuestion

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

SUBMIT = "/api/v1/assignments/{}/submit"
DECLARED = {"ai_use": "none", "statement": "Я написал эту работу сам."}

YESTERDAY = datetime.now(UTC) - timedelta(days=1)
TOMORROW = datetime.now(UTC) + timedelta(days=1)


def _as_teacher(db: Session, teacher) -> TestClient:
    """A second signed-in client for the marking side.

    ``client`` and ``student_client`` share one ``dependency_overrides`` slot,
    so whichever fixture was built last answers for both; the teacher's calls
    here come *after* the student's, so they get their own client.
    """

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: teacher
    app.dependency_overrides[get_optional_user] = lambda: teacher
    return TestClient(app, raise_server_exceptions=False)


def _assignment(db: Session, course_id: str, *, due: datetime | None) -> Assignment:
    course = Course(id=course_id, status="published", created_by=TEACHER_ID)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.flush()
    chapter = Chapter(id=f"{course_id}-a", module_id=module.id, order_index=0, chapter_type="assignment", title="Эссе")
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100, due_date=due)
    db.add(assignment)
    db.commit()
    return assignment


def _quiz(db: Session, course_id: str, *, module_due: datetime | None) -> tuple[Quiz, QuizQuestion]:
    course = Course(id=course_id, status="published", created_by=TEACHER_ID, source_locale="en")
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M", due_date=module_due)
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.flush()
    chapter = Chapter(id=f"{course_id}-q", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=50)
    db.add(quiz)
    db.flush()
    essay = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=5, order_index=0)
    db.add(essay)
    db.commit()
    return quiz, essay


class TestAssignments:
    def test_late_work_is_accepted_and_marked(self, student_client: TestClient, db: Session, teacher, student) -> None:
        assignment = _assignment(db, "late-accepted", due=YESTERDAY)

        resp = student_client.post(SUBMIT.format(assignment.id), json={"content": "Поздно", "declaration": DECLARED})

        assert resp.status_code == 201, resp.text
        assert resp.json()["is_late"] is True

    def test_work_in_time_is_not(self, student_client: TestClient, db: Session, teacher, student) -> None:
        assignment = _assignment(db, "late-in-time", due=TOMORROW)

        resp = student_client.post(SUBMIT.format(assignment.id), json={"content": "Вовремя", "declaration": DECLARED})

        assert resp.status_code == 201, resp.text
        assert resp.json()["is_late"] is False

    def test_no_deadline_means_nothing_is_late(self, student_client: TestClient, db: Session, teacher, student) -> None:
        assignment = _assignment(db, "late-no-deadline", due=None)

        resp = student_client.post(
            SUBMIT.format(assignment.id), json={"content": "Когда-нибудь", "declaration": DECLARED}
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["is_late"] is False

    def test_the_student_sees_it_on_their_own_history(
        self, student_client: TestClient, db: Session, teacher, student
    ) -> None:
        assignment = _assignment(db, "late-own-history", due=YESTERDAY)
        student_client.post(SUBMIT.format(assignment.id), json={"content": "Поздно", "declaration": DECLARED})

        mine = student_client.get(f"/api/v1/assignments/{assignment.id}/my-submissions").json()

        assert [s["is_late"] for s in mine] == [True]

    def test_the_teacher_sees_it_in_the_list_and_the_queue(
        self, student_client: TestClient, db: Session, teacher, student
    ) -> None:
        assignment = _assignment(db, "late-teacher-side", due=YESTERDAY)
        student_client.post(SUBMIT.format(assignment.id), json={"content": "Поздно", "declaration": DECLARED})

        client = _as_teacher(db, teacher)
        listed = client.get(f"/api/v1/assignments/{assignment.id}/submissions").json()
        queued = client.get(f"/api/v1/grades/queue/assignment/{assignment.id}").json()

        assert [s["is_late"] for s in listed] == [True]
        assert [s["is_late"] for s in queued] == [True]

    def test_marking_it_keeps_the_flag(self, student_client: TestClient, db: Session, teacher, student) -> None:
        """The mark does not launder the lateness: the graded row still says so."""
        assignment = _assignment(db, "late-then-marked", due=YESTERDAY)
        submission_id = student_client.post(
            SUBMIT.format(assignment.id), json={"content": "Поздно", "declaration": DECLARED}
        ).json()["id"]

        graded = _as_teacher(db, teacher).put(
            f"/api/v1/assignments/submissions/{submission_id}/grade", json={"grade": 70}
        )

        assert graded.status_code == 200, graded.text
        assert graded.json()["is_late"] is True

    def test_a_revision_the_teacher_asked_for_is_not_late(
        self, student_client: TestClient, db: Session, teacher, student
    ) -> None:
        """Handed in on time, returned for revision, revised after the date:
        the deadline was met — the first hand-in decides (2026-10-03)."""
        from app.models.assignment import AssignmentSubmission

        assignment = _assignment(db, "late-revision", due=YESTERDAY)
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment.id,
                student_id=STUDENT_ID,
                content="Вовремя",
                status="returned",
                submitted_at=YESTERDAY - timedelta(days=2),
            )
        )
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment.id,
                student_id=STUDENT_ID,
                content="Доработано",
                status="submitted",
                submitted_at=datetime.now(UTC),
            )
        )
        db.commit()

        mine = student_client.get(f"/api/v1/assignments/{assignment.id}/my-submissions").json()
        queued = _as_teacher(db, teacher).get(f"/api/v1/grades/queue/assignment/{assignment.id}").json()

        assert [s["is_late"] for s in mine] == [False, False]
        assert [s["is_late"] for s in queued] == [False]


class TestQuizzes:
    def test_an_attempt_after_the_modules_due_date_is_late(
        self, student_client: TestClient, db: Session, teacher, student
    ) -> None:
        quiz, essay = _quiz(db, "late-quiz", module_due=YESTERDAY)

        submitted = student_client.post(
            f"/api/v1/quizzes/{quiz.id}/submit",
            json={"answers": [{"question_id": str(essay.id), "text_answer": "Поздний ответ"}]},
        )
        mine = student_client.get(f"/api/v1/quizzes/{quiz.id}/my-attempts").json()
        client = _as_teacher(db, teacher)
        theirs = client.get(f"/api/v1/quizzes/{quiz.id}/attempts").json()
        pending = client.get(f"/api/v1/quizzes/{quiz.id}/pending-answers").json()

        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["is_late"] is True
        assert [a["is_late"] for a in mine] == [True]
        assert [a["is_late"] for a in theirs] == [True]
        assert [p["is_late"] for p in pending] == [True]

    def test_a_module_without_a_due_date_has_no_late_attempts(
        self, student_client: TestClient, db: Session, teacher, student
    ) -> None:
        quiz, essay = _quiz(db, "late-quiz-undated", module_due=None)

        submitted = student_client.post(
            f"/api/v1/quizzes/{quiz.id}/submit",
            json={"answers": [{"question_id": str(essay.id), "text_answer": "Ответ"}]},
        )

        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["is_late"] is False
