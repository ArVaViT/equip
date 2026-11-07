"""«With honors» — the teacher's one switch, frozen onto each certificate (Q3).

Off by default. When a course offers it, a student whose official grade sits in
the top band of the course's scheme (A, 5) gets «with honors» on the
certificate and the transcript line. Decided at approval and never again:
switching it off next year takes nothing back from anyone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.models.audit_log import AuditLog
from app.models.certificate import Certificate, CertificateStatus
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAttempt
from app.models.student_grade import StudentGrade
from app.services.certificate_grade_snapshot import snapshot_certificate_grade

from .conftest import STUDENT_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

HONORS_URL = "/api/v1/grades/course/{course_id}/honors"
SCHEME_URL = "/api/v1/grades/course/{course_id}/scheme"


def _course(
    db: Session,
    teacher,
    course_id: str,
    *,
    score: int | None = 95,
    scheme: str = "letter",
    with_honors: bool = True,
    hours: int | None = None,
) -> Course:
    """A one-quiz course the seeded student finished with *score* (no quiz when ``None``)."""
    course = Course(
        id=course_id,
        status="published",
        created_by=teacher.id,
        quiz_weight=100,
        assignment_weight=0,
        grading_scheme=scheme,
        pass_threshold=Decimal("60.00") if scheme == "five_point" else Decimal("70.00"),
        with_honors=with_honors,
        academic_hours=hours,
    )
    db.add(course)
    db.flush()
    if score is not None:
        module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
        db.add(module)
        db.flush()
        chapter = Chapter(id=f"{course_id}-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
        db.add(chapter)
        db.flush()
        quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
        db.add(quiz)
        db.flush()
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz.id,
                user_id=STUDENT_ID,
                score=score,
                max_score=100,
                passed=True,
                completed_at=datetime.now(UTC),
            )
        )
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=100))
    db.commit()
    return course


def _issue(db: Session, course: Course) -> Certificate:
    cert = Certificate(id=uuid.uuid4(), user_id=STUDENT_ID, course_id=course.id, status=CertificateStatus.APPROVED)
    db.add(cert)
    db.flush()
    snapshot_certificate_grade(db, cert, course)
    db.commit()
    return cert


# --------------------------------------------------------------------------
# Who earns it
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scheme", "score", "with_honors", "expected"),
    [
        ("letter", 95, True, True),
        ("letter", 85, True, False),
        ("letter", 95, False, False),
        ("five_point", 96, True, True),
        ("five_point", 80, True, False),
        ("percent", 99, True, False),
        ("pass_fail", 99, True, False),
    ],
    ids=[
        "letter-A-on",
        "letter-B-on",
        "letter-A-off",
        "five-point-5-on",
        "five-point-4-on",
        "percent-never",
        "pass-fail-never",
    ],
)
def test_only_the_top_band_of_a_course_that_offers_it_earns_honors(
    db: Session, teacher, student, scheme: str, score: int, with_honors: bool, expected: bool
) -> None:
    course = _course(db, teacher, f"c-hon-{scheme}-{score}-{with_honors}", score=score, scheme=scheme)
    course.with_honors = with_honors
    db.commit()

    assert _issue(db, course).with_honors is expected


def test_a_hand_set_top_grade_earns_it(db: Session, teacher, student) -> None:
    """The override IS the official grade (D7), so it decides honors too."""
    course = _course(db, teacher, "c-hon-override", score=40)
    db.add(StudentGrade(course_id=course.id, student_id=STUDENT_ID, override_code="A"))
    db.commit()

    cert = _issue(db, course)

    assert cert.official_code == "A"
    assert cert.with_honors is True


def test_a_certificate_issued_on_completion_alone_does_not(db: Session, teacher, student) -> None:
    """Honors is a statement about a grade; no grade was ever computed here."""
    course = _course(db, teacher, "c-hon-completion", score=None)

    cert = _issue(db, course)

    assert cert.graded_via == "completion"
    assert cert.with_honors is False


def test_switching_it_off_takes_nothing_back(db: Session, teacher, student) -> None:
    course = _course(db, teacher, "c-hon-frozen", score=97, hours=36)
    cert = _issue(db, course)
    assert cert.with_honors is True

    course.with_honors = False
    course.academic_hours = 72
    db.commit()
    db.refresh(cert)

    assert cert.with_honors is True, "the paper in the folder still says what it said"
    assert cert.academic_hours == 36, "the hours are the ones the course carried at issuance"


# --------------------------------------------------------------------------
# The switch
# --------------------------------------------------------------------------


def test_the_teacher_turns_it_on_and_it_is_written_down(client, db: Session, teacher, student) -> None:
    course = _course(db, teacher, "c-hon-switch", score=None, with_honors=False)
    assert client.get(SCHEME_URL.format(course_id=course.id)).json()["with_honors"] is False

    resp = client.put(HONORS_URL.format(course_id=course.id), json={"with_honors": True})

    assert resp.status_code == 200, resp.text
    assert resp.json()["with_honors"] is True
    db.refresh(course)
    assert course.with_honors is True
    assert client.get(SCHEME_URL.format(course_id=course.id)).json()["with_honors"] is True
    entry = db.query(AuditLog).filter(AuditLog.action == "with_honors_changed").one()
    assert entry.resource_id == course.id


def test_a_course_starts_without_it(db: Session, teacher) -> None:
    course = Course(id="c-hon-default", status="published", created_by=teacher.id)
    db.add(course)
    db.commit()
    db.refresh(course)

    assert course.with_honors is False


@pytest.mark.parametrize("scheme", ["pass_fail", "percent"], ids=["pass-fail", "percent"])
def test_a_scheme_without_bands_has_no_top_band_to_honour(client, db: Session, teacher, student, scheme: str) -> None:
    course = _course(db, teacher, f"c-hon-noband-{scheme}", score=None, scheme=scheme, with_honors=False)

    resp = client.put(HONORS_URL.format(course_id=course.id), json={"with_honors": True})

    assert resp.status_code == 422, resp.text
    db.refresh(course)
    assert course.with_honors is False


def test_a_student_cannot_flip_it(student_client, db: Session, teacher) -> None:
    course = _course(db, teacher, "c-hon-student", score=None, with_honors=False)

    resp = student_client.put(HONORS_URL.format(course_id=course.id), json={"with_honors": True})

    assert resp.status_code == 403, resp.text
    db.refresh(course)
    assert course.with_honors is False


# --------------------------------------------------------------------------
# What the student's own list carries — the transcript's source
# --------------------------------------------------------------------------


def test_my_certificates_carry_the_snapshot_the_transcript_prints(student_client, db: Session, teacher) -> None:
    course = _course(db, teacher, "c-hon-mine", score=95, hours=24)
    cert = _issue(db, course)
    cert.certificate_number = "EQ-HONORS-1"
    cert.issued_at = datetime.now(UTC)
    db.commit()

    rows = student_client.get("/api/v1/certificates/my").json()

    row = next(r for r in rows if r["id"] == str(cert.id))
    assert row["grading_scheme"] == "letter"
    assert row["official_code"] == "A"
    assert row["with_honors"] is True
    assert row["academic_hours"] == 24
