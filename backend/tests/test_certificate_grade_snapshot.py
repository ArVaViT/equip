"""The grade a certificate was issued on stays what it was (M6).

Everything a certificate is computed from is live and editable — the course
weights, the school's grade bands, the pass line, the student's marks, whether
a piece of work was excused. A certificate that recomputed on read would change
years after it was signed, silently, for everyone who ever graduated.

So the tests that matter here are not "does it write the right number" but
"does the number survive the inputs changing underneath it".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.certificate import Certificate, CertificateStatus
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.org_settings import OrgSettings
from app.models.quiz import Quiz, QuizAttempt
from app.models.student_grade import StudentGrade
from app.models.user import User
from app.services.certificate_grade_snapshot import snapshot_certificate_grade

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

ADMIN_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


def _graded_course(db: Session, teacher, course_id: str, *, score: int = 95, quizzes: int = 1):
    course = Course(
        id=course_id,
        status="published",
        created_by=teacher.id,
        quiz_weight=100,
        assignment_weight=0,
        grading_scheme="letter",
        pass_threshold=Decimal("70.00"),
    )
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    for i in range(quizzes):
        chapter = Chapter(
            id=f"{course_id}-ch{i}", module_id=module.id, order_index=i, chapter_type="quiz", title=f"Q{i}"
        )
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


def _certificate(db: Session, course_id: str | None) -> Certificate:
    cert = Certificate(
        id=uuid.uuid4(),
        user_id=STUDENT_ID,
        course_id=course_id,
        status=CertificateStatus.TEACHER_APPROVED,
    )
    db.add(cert)
    db.commit()
    return cert


def test_the_snapshot_records_the_rules_in_force(db: Session, teacher, student) -> None:
    """A transcript must render «4 (хорошо)» years after the school moved to
    letters. That needs the scheme, not just the symbol."""
    course = _graded_course(db, teacher, "c-snap-rules")
    cert = _certificate(db, course.id)

    snapshot_certificate_grade(db, cert, course)
    db.commit()

    assert cert.grading_scheme == "letter"
    assert cert.pass_threshold == Decimal("70.00")
    assert cert.official_code == "A"
    assert cert.official_score is None
    assert cert.graded_via == "computed"


def test_moving_the_schools_bands_does_not_move_an_issued_certificate(db: Session, teacher, student) -> None:
    """The whole point. A director nudges the band table and every certificate
    ever issued would otherwise change, retroactively and without a word."""
    course = _graded_course(db, teacher, "c-snap-frozen", score=91)
    cert = _certificate(db, course.id)
    snapshot_certificate_grade(db, cert, course)
    db.commit()
    assert cert.official_code == "A"

    settings = db.query(OrgSettings).first()
    settings.grade_bands = {"letter": [[95, "A"], [85, "B"], [75, "C"], [65, "D"], [0, "F"]]}
    db.commit()
    db.refresh(cert)

    assert cert.official_code == "A", "the paper in the folder still says what it said"


def test_a_later_regrade_does_not_move_an_issued_certificate(db: Session, teacher, student) -> None:
    course = _graded_course(db, teacher, "c-snap-regrade", score=95)
    cert = _certificate(db, course.id)
    snapshot_certificate_grade(db, cert, course)
    db.commit()

    # The teacher re-marks the quiz down to a failure long after issuance.
    attempt = db.query(QuizAttempt).filter(QuizAttempt.user_id == STUDENT_ID).first()
    attempt.score = 10
    db.commit()
    db.refresh(cert)

    assert cert.official_code == "A"


def test_a_hand_set_grade_is_what_gets_certified(db: Session, teacher, student) -> None:
    """The override IS the official grade (D7) — it decides the certificate, so
    it is the thing the certificate has to carry."""
    course = _graded_course(db, teacher, "c-snap-override", score=30)
    db.add(StudentGrade(course_id=course.id, student_id=STUDENT_ID, override_code="B"))
    db.commit()
    cert = _certificate(db, course.id)

    snapshot_certificate_grade(db, cert, course)
    db.commit()

    assert cert.official_code == "B"
    assert cert.graded_via == "override"


def test_a_numeric_override_is_recorded_as_a_score(db: Session, teacher, student) -> None:
    course = _graded_course(db, teacher, "c-snap-override-num", score=30)
    course.grading_scheme = "percent"
    db.add(StudentGrade(course_id=course.id, student_id=STUDENT_ID, override_score=Decimal("88.50")))
    db.commit()
    cert = _certificate(db, course.id)

    snapshot_certificate_grade(db, cert, course)
    db.commit()

    assert cert.official_score == Decimal("88.50")
    assert cert.official_code is None
    assert cert.graded_via == "override"


def test_a_course_with_nothing_gradable_is_certified_on_completion(db: Session, teacher, student) -> None:
    """Most of the certificates on this platform have this shape.

    Writing a 0 here would print a failure onto a credential that was issued on
    completion — the exact lie the `completion_pass` state exists to prevent.
    """
    course = Course(id="c-snap-completion", status="published", created_by=teacher.id, grading_scheme="letter")
    db.add(course)
    db.add(Enrollment(id="enr-c-snap-completion", user_id=STUDENT_ID, course_id=course.id, progress=100))
    db.commit()
    cert = _certificate(db, course.id)

    snapshot_certificate_grade(db, cert, course)
    db.commit()

    assert cert.graded_via == "completion"
    assert cert.official_code is None
    assert cert.official_score is None
    assert cert.grading_scheme == "letter", "the rules are still worth recording"


def test_a_percent_course_records_a_number_not_a_symbol(db: Session, teacher, student) -> None:
    course = _graded_course(db, teacher, "c-snap-percent", score=83)
    course.grading_scheme = "percent"
    db.commit()
    cert = _certificate(db, course.id)

    snapshot_certificate_grade(db, cert, course)
    db.commit()

    assert cert.official_score == Decimal("83.0")
    assert cert.official_code is None


def test_a_deleted_course_leaves_the_snapshot_blank_rather_than_guessed(db: Session, teacher, student) -> None:
    """NULL means "the platform did not record this", which is the truth. A
    guess would be worse than a gap on a document someone signs."""
    # `certificates.course_id` is ON DELETE SET NULL — deleting a course leaves
    # the credential standing with no course behind it.
    cert = _certificate(db, None)

    snapshot_certificate_grade(db, cert, None)
    db.commit()

    assert cert.grading_scheme is None
    assert cert.graded_via is None


# --------------------------------------------------------------------------
# through the real issuance route
# --------------------------------------------------------------------------


def test_issuing_a_certificate_writes_the_snapshot(client, db: Session, teacher, student) -> None:
    from app.api.dependencies import require_admin
    from app.main import app

    course = _graded_course(db, teacher, "c-snap-route", score=95)
    admin = User(id=ADMIN_ID, email="admin@example.com", full_name="Admin", role="admin")
    db.add(admin)
    cert = _certificate(db, course.id)
    cert.teacher_approved_by = TEACHER_ID
    cert.teacher_approved_at = datetime.now(UTC)
    db.commit()

    app.dependency_overrides[require_admin] = lambda: admin
    try:
        resp = client.put(f"/api/v1/certificates/{cert.id}/admin-approve")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert resp.status_code == 200, resp.text
    db.refresh(cert)
    assert cert.official_code == "A"
    assert cert.graded_via == "computed"
    assert cert.grading_scheme == "letter"
