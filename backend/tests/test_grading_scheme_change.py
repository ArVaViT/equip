"""Changing how a course is graded — D8.

Until now there was no way to change a course's scheme at all: no field, no
route. That absence was also the only thing preventing the change from being
made silently, so the write path arrives with its rules already attached
rather than acquiring them later.

Three rules, each protecting something different:

* the scheme and its pass line are written together, because a five-point
  course whose pass line sits above 75 has an unreachable «3» band and no
  single-value write can notice that;
* hand-set grades block a scheme change, because «A» is not a five-point grade
  and reinterpreting it would move a student's official result without anyone
  deciding to;
* the change is audited, because it redefines what every grade in the course
  means — an academic decision, not a settings tweak.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.audit_log import AuditLog
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz
from app.models.student_grade import StudentGrade

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

SCHEME_URL = "/api/v1/grades/course/{course_id}/scheme"


def _course(db: Session, teacher, course_id: str = "c-scheme-change", scheme: str = "letter") -> Course:
    course = Course(id=course_id, status="published", created_by=teacher.id, grading_scheme=scheme)
    db.add(course)
    db.commit()
    return course


def test_reading_the_scheme_returns_the_bands_it_is_read_against(admin_client, db: Session, teacher) -> None:
    """The client should render from the backend's answer, not its own copy."""
    course = _course(db, teacher)

    body = admin_client.get(SCHEME_URL.format(course_id=course.id)).json()

    assert body["grading_scheme"] == "letter"
    assert [b[1] for b in body["bands"]] == ["A", "B", "C", "D", "F"]


def test_scheme_and_threshold_change_together(admin_client, db: Session, teacher) -> None:
    course = _course(db, teacher)

    resp = admin_client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "five_point", "pass_threshold": "70", "reason": "School switched to 5-point"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["grading_scheme"] == "five_point"
    assert [b[1] for b in resp.json()["bands"]] == ["5", "4", "3", "2"]


def test_five_point_above_the_ceiling_is_refused(admin_client, db: Session, teacher) -> None:
    """A pass line above 75 leaves «3 (удовлетворительно)» unreachable.

    The course would look ordinary and be impossible to pass at the grade the
    scheme's own vocabulary calls passing.
    """
    course = _course(db, teacher)

    resp = admin_client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "five_point", "pass_threshold": "80"},
    )

    assert resp.status_code == 422
    assert "75" in resp.text


def test_existing_hand_set_grades_block_a_scheme_change(admin_client, db: Session, teacher, student) -> None:
    """«A» is not a grade in a five-point course.

    Converting it silently would change a student's official result with
    nobody having decided to. The refusal names who is affected so the teacher
    can act deliberately.
    """
    from .conftest import STUDENT_ID

    course = _course(db, teacher, course_id="c-scheme-blocked")
    db.add(Enrollment(id="enr-blocked", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.add(
        StudentGrade(
            id=uuid.uuid4(),
            student_id=STUDENT_ID,
            course_id=course.id,
            override_code="A",
        )
    )
    db.commit()

    resp = admin_client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "five_point", "pass_threshold": "70"},
    )

    assert resp.status_code == 409
    assert str(STUDENT_ID) in resp.text
    db.refresh(course)
    assert course.grading_scheme == "letter", "the course must not change while overrides stand"


def test_threshold_alone_may_move_with_overrides_present(admin_client, db: Session, teacher, student) -> None:
    """Only a *scheme* change reinterprets existing symbols.

    Nudging the pass line inside the same scheme does not make an «A» mean
    something else, so blocking it would be strictness without a reason.
    """
    from .conftest import STUDENT_ID

    course = _course(db, teacher, course_id="c-threshold-only")
    db.add(Enrollment(id="enr-thresh", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.add(StudentGrade(id=uuid.uuid4(), student_id=STUDENT_ID, course_id=course.id, override_code="B"))
    db.commit()

    resp = admin_client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "letter", "pass_threshold": "75"},
    )

    assert resp.status_code == 200
    db.refresh(course)
    assert float(course.pass_threshold) == 75.0


def test_the_change_is_written_down(admin_client, db: Session, teacher) -> None:
    course = _course(db, teacher, course_id="c-scheme-audit")

    admin_client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "percent", "pass_threshold": "60", "reason": "Director's decision"},
    )

    entry = db.query(AuditLog).filter(AuditLog.action == "grading_scheme_changed").first()
    assert entry is not None, "redefining what every grade means must leave a trail"
    assert entry.details["previous"]["grading_scheme"] == "letter"
    assert entry.details["new"]["grading_scheme"] == "percent"
    assert entry.details["reason"] == "Director's decision"


def test_a_teacher_cannot_change_how_their_own_course_is_graded(client, db: Session, teacher) -> None:
    """A director's decision, not a teacher's (D1).

    Left to each teacher, one school's transcript ends up mixing «зачёт»,
    «4 (хорошо)» and «B» across its own courses — and the transcript is the
    artifact the school is judged on. The teacher owns this course; they still
    cannot decide alone what its grades mean.
    """
    course = Course(id="c-teacher-cannot", status="published", created_by=teacher.id)
    db.add(course)
    db.commit()

    resp = client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "percent", "pass_threshold": "60"},
    )

    assert resp.status_code == 403
    db.refresh(course)
    assert course.grading_scheme == "letter", "and nothing moved"


def test_a_teacher_can_still_see_how_their_course_is_graded(client, db: Session, teacher) -> None:
    """Read stays open. A teacher who cannot see the pass line cannot explain a
    grade to the student sitting in front of them."""
    course = Course(id="c-teacher-can-read", status="published", created_by=teacher.id)
    db.add(course)
    db.commit()

    resp = client.get(SCHEME_URL.format(course_id=course.id))

    assert resp.status_code == 200
    assert resp.json()["grading_scheme"] == "letter"
    assert resp.json()["bands"], "including the bands their grades are read against"


def test_a_director_may_change_a_course_they_do_not_teach(admin_client, db: Session, teacher) -> None:
    """Which is the whole point of it being an institutional call."""
    from app.models.user import User, UserRole

    other_teacher = User(
        id=uuid.uuid4(),
        email="other-teacher@test.local",
        full_name="Other Teacher",
        role=UserRole.TEACHER,
    )
    db.add(other_teacher)
    db.flush()
    foreign = Course(id="c-foreign-scheme", status="published", created_by=other_teacher.id)
    db.add(foreign)
    db.commit()

    resp = admin_client.put(
        SCHEME_URL.format(course_id=foreign.id),
        json={"grading_scheme": "percent", "pass_threshold": "60"},
    )

    assert resp.status_code == 200
    db.refresh(foreign)
    assert foreign.grading_scheme == "percent"


class TestQuizThresholdAlignment:
    """The two pass lines must not drift apart (D3).

    `quizzes.passing_score` gates chapter completion; `courses.pass_threshold`
    is the course result line. A quiz defaulting to a hardcoded 70 inside a
    course that passes at 80 produces the trap the design names: the student
    clears every quiz, reaches progress 100, and still cannot pass — or the
    reverse, a stricter quiz keeps the chapter incomplete so the certificate
    stays out of reach with nothing on screen explaining why.
    """

    def test_a_new_quiz_inherits_the_course_pass_line(self, client, db: Session, teacher) -> None:
        from app.models.course import Chapter, Module
        from app.models.quiz import Quiz

        course = _course(db, teacher, course_id="c-quiz-inherit")
        course.pass_threshold = 85
        module = Module(id="m-inherit", course_id=course.id, order_index=0, title="M")
        db.add(module)
        db.flush()
        chapter = Chapter(id="ch-inherit", module_id=module.id, order_index=0, chapter_type="quiz", title="Ch")
        db.add(chapter)
        db.commit()

        resp = client.post(
            "/api/v1/quizzes",
            json={"chapter_id": chapter.id, "title": "Quiz 1", "questions": []},
        )

        assert resp.status_code in (200, 201), resp.text
        quiz = db.query(Quiz).filter(Quiz.chapter_id == chapter.id).first()
        assert quiz is not None
        assert quiz.passing_score == 85, "a quiz must not silently demand less than its course"

    def test_an_explicit_threshold_still_wins(self, client, db: Session, teacher) -> None:
        """Inheriting is a default, not a rule — a teacher may still differ."""
        from app.models.course import Chapter, Module
        from app.models.quiz import Quiz

        course = _course(db, teacher, course_id="c-quiz-explicit")
        course.pass_threshold = 85
        module = Module(id="m-explicit", course_id=course.id, order_index=0, title="M")
        db.add(module)
        db.flush()
        chapter = Chapter(id="ch-explicit", module_id=module.id, order_index=0, chapter_type="quiz", title="Ch")
        db.add(chapter)
        db.commit()

        client.post(
            "/api/v1/quizzes",
            json={"chapter_id": chapter.id, "title": "Quiz 1", "passing_score": 60, "questions": []},
        )

        quiz = db.query(Quiz).filter(Quiz.chapter_id == chapter.id).first()
        assert quiz.passing_score == 60


def test_moving_the_course_line_records_which_quizzes_it_leaves_behind(
    admin_client, db: Session, teacher, student
) -> None:
    """A quiz keeps the pass line it was written with.

    Raise the course's and a student clears every quiz, is congratulated each
    time, and still lands below the mark the course grades them on — with every
    chapter green. The drift is invisible from the settings screen, so it goes
    into the audit entry: "the line moved to 85 and these quizzes stayed at 60"
    is the sentence a director needs, and nobody can reconstruct it later.
    """
    course = Course(id="c-drift", status="published", created_by=teacher.id, pass_threshold=Decimal("60.00"))
    db.add(course)
    module = Module(id="c-drift-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-drift-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    db.add(Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=60))
    db.commit()

    resp = admin_client.put(
        f"/api/v1/grades/course/{course.id}/scheme",
        json={"grading_scheme": "letter", "pass_threshold": 85},
    )

    assert resp.status_code == 200, resp.text
    entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == "grading_scheme_changed")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    drifted = entry.details["quizzes_off_the_new_line"]
    assert len(drifted) == 1
    assert drifted[0]["passing_score"] == 60


def test_a_quiz_easier_than_its_course_is_flagged_by_readiness(db: Session, teacher) -> None:
    """The mirror of the check that already existed, and the one nobody thinks
    of: drift one way was caught, drift the other way was silent."""
    from app.services.course_readiness import compute_readiness

    course = Course(
        id="c-lenient",
        status="published",
        created_by=teacher.id,
        pass_threshold=Decimal("85.00"),
        title="Lenient",
    )
    db.add(course)
    module = Module(id="c-lenient-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-lenient-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    db.add(Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=60))
    db.commit()

    report = compute_readiness(db, course)
    failing = {c.id for c in report.checks if not c.passed}

    assert "quiz_threshold_below_course" in failing


def test_a_quiz_stricter_than_its_course_is_still_flagged(db: Session, teacher) -> None:
    from app.services.course_readiness import compute_readiness

    course = Course(
        id="c-strict",
        status="published",
        created_by=teacher.id,
        pass_threshold=Decimal("60.00"),
        title="Strict",
    )
    db.add(course)
    module = Module(id="c-strict-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-strict-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    db.add(Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=90))
    db.commit()

    report = compute_readiness(db, course)
    failing = {c.id for c in report.checks if not c.passed}

    assert "quiz_threshold_above_course" in failing
