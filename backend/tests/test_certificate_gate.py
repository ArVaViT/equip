"""The certificate gate (D9) — the last thing this phase adds.

It ships behind its own explanation on purpose. The reason list this refusal
carries has been on the student's course page since #962 and the recovery path
since #963, so nobody meets a refusal here for the first time.

What it closes: an assignment chapter completes on **submission**, so before
this a student could finish a course with every essay unread and be handed a
certificate saying so. No "all items graded" machinery was needed for it —
unmarked work holds итоговая under the pass line on its own.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.certificate import Certificate, CertificateStatus
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

URL = "/api/v1/certificates/course/{}"


def _course(db: Session, course_id: str, *, scheme: str = "letter", progress: int = 100):
    course = Course(
        id=course_id,
        status="published",
        created_by=TEACHER_ID,
        grading_scheme=scheme,
        pass_threshold=70,
    )
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=progress))
    db.flush()
    return course, module


def _assignment(db: Session, module, course_id: str, *, status: str | None, grade: int | None):
    chapter = Chapter(
        id=f"{course_id}-a",
        module_id=module.id,
        order_index=0,
        chapter_type="assignment",
        title="Эссе",
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    if status is not None:
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment.id,
                student_id=STUDENT_ID,
                status=status,
                grade=grade,
            )
        )
    return assignment


def _codes(response) -> list[str]:
    return [b["code"] for b in response.json()["detail"]["context"]["blockers"]]


def test_a_course_finished_with_every_essay_unread_no_longer_certifies_itself(
    student_client, db: Session, teacher, student
) -> None:
    """The loophole this gate exists for. An assignment chapter completes on
    submission, so progress reaches 100 with nothing marked — and the old check
    was progress alone. The certificate would have said the course was passed
    on the strength of work nobody had opened."""
    course, module = _course(db, "gate-unread")
    _assignment(db, module, course.id, status="submitted", grade=None)
    db.commit()

    response = student_client.post(URL.format(course.id))

    assert response.status_code == 400, response.text
    assert _codes(response) == ["work_not_graded"]
    assert db.query(Certificate).count() == 0


def test_a_student_who_passed_still_gets_one(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "gate-passed")
    _assignment(db, module, course.id, status="graded", grade=88)
    db.commit()

    response = student_client.post(URL.format(course.id))

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "pending"


def test_a_failing_score_is_refused_with_the_line_it_missed(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "gate-failed")
    _assignment(db, module, course.id, status="graded", grade=64)
    db.commit()

    response = student_client.post(URL.format(course.id))

    assert response.status_code == 400
    blocker = response.json()["detail"]["context"]["blockers"][0]
    assert blocker["code"] == "below_threshold"
    assert blocker["params"] == {"final_score": 64.0, "pass_threshold": 70.0, "provisional": False}


def test_a_course_with_nothing_gradable_in_it_certifies_completion(
    student_client, db: Session, teacher, student
) -> None:
    """The shape most certificates on this platform have come from: a reading
    course with no quiz and no essay. There is nothing to pass, and completion
    is the whole of the claim (D4's vacuous rule)."""
    _course(db, "gate-reading")
    db.commit()

    assert student_client.post(URL.format("gate-reading")).status_code == 201


def test_an_unfinished_course_is_refused_as_before(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "gate-progress", progress=40)
    _assignment(db, module, course.id, status="graded", grade=95)
    db.commit()

    response = student_client.post(URL.format(course.id))

    assert response.status_code == 400
    assert _codes(response)[0] == "course_not_complete"


# ---------------------------------------------------------------------------
# What the gate must not touch
# ---------------------------------------------------------------------------


def test_a_certificate_already_issued_is_not_reexamined(student_client, db: Session, teacher, student) -> None:
    """A document is judged by the rules in force when it was granted, or
    nobody can rely on holding one (D8.3). The four issued before this gate
    existed keep standing, and so will every one issued under a rule that
    changes later."""
    course, module = _course(db, "gate-grandfathered")
    _assignment(db, module, course.id, status="submitted", grade=None)
    db.add(
        Certificate(
            id=uuid.uuid4(),
            user_id=STUDENT_ID,
            course_id=course.id,
            status=CertificateStatus.APPROVED,
            issued_at=datetime.now(UTC),
        )
    )
    db.commit()

    response = student_client.post(URL.format(course.id))

    assert response.status_code == 201
    assert response.json()["status"] == "approved"


def test_a_pending_request_is_not_re_examined_either(student_client, db: Session, teacher, student) -> None:
    """Otherwise a student who asked yesterday, before their teacher marked
    anything, has their own pending request turned into an error the next time
    the page loads."""
    course, module = _course(db, "gate-pending")
    _assignment(db, module, course.id, status="submitted", grade=None)
    db.add(
        Certificate(
            id=uuid.uuid4(),
            user_id=STUDENT_ID,
            course_id=course.id,
            status=CertificateStatus.PENDING,
        )
    )
    db.commit()

    assert student_client.post(URL.format(course.id)).status_code == 201


def test_asking_again_after_a_rejection_meets_the_same_gate(student_client, db: Session, teacher, student) -> None:
    """A re-request is a new request. Without this, one rejection is the way
    around the gate — reject, re-request, and the row reopens unexamined."""
    course, module = _course(db, "gate-rejected")
    _assignment(db, module, course.id, status="submitted", grade=None)
    db.add(
        Certificate(
            id=uuid.uuid4(),
            user_id=STUDENT_ID,
            course_id=course.id,
            status=CertificateStatus.REJECTED,
        )
    )
    db.commit()

    response = student_client.post(URL.format(course.id))

    assert response.status_code == 400
    assert (
        db.query(Certificate).filter(Certificate.course_id == course.id).one().status == CertificateStatus.REJECTED
    ), "and the rejected row stays rejected rather than half-reopening"


def test_the_gate_reads_this_terms_enrolment_not_last_terms(student_client, db: Session, teacher, student) -> None:
    """A retaking student holds two enrolments. Gating this term's certificate
    on last term's progress is a decision made by row order, and it goes both
    ways: refusing someone who finished, or certifying someone who has not
    started."""
    course, module = _course(db, "gate-retake", progress=100)
    _assignment(db, module, course.id, status="graded", grade=95)
    db.add(
        Enrollment(
            id="enr-gate-retake-2",
            user_id=STUDENT_ID,
            course_id=course.id,
            progress=10,
            enrolled_at=datetime.now(UTC),
        )
    )
    db.query(Enrollment).filter(Enrollment.id == "enr-gate-retake").update(
        {"enrolled_at": datetime(2025, 1, 1, tzinfo=UTC)}
    )
    db.commit()

    response = student_client.post(URL.format(course.id))

    assert response.status_code == 400
    assert _codes(response)[0] == "course_not_complete"
    assert response.json()["detail"]["context"]["blockers"][0]["params"]["progress"] == 10


def test_a_reviewer_sees_what_is_still_missing_before_they_sign(client, db: Session, teacher, student) -> None:
    """A request raised before the gate existed — or before the teacher marked
    the last essay — arrives on the pending card looking exactly like an earned
    one. Approving it is a signature on a document saying the course was
    passed, and the person signing should not have to open the gradebook in
    another tab to find out whether that is true."""
    course, module = _course(db, "gate-review")
    _assignment(db, module, course.id, status="submitted", grade=None)
    db.add(
        Certificate(
            id=uuid.uuid4(),
            user_id=STUDENT_ID,
            course_id=course.id,
            status=CertificateStatus.PENDING,
        )
    )
    db.commit()

    rows = client.get("/api/v1/certificates/pending").json()

    assert [b["code"] for b in rows[0]["blockers"]] == ["work_not_graded"]


def test_an_earned_request_carries_no_warning(client, db: Session, teacher, student) -> None:
    """An empty list on every row would be a badge nobody reads."""
    course, module = _course(db, "gate-review-clean")
    _assignment(db, module, course.id, status="graded", grade=91)
    db.add(
        Certificate(
            id=uuid.uuid4(),
            user_id=STUDENT_ID,
            course_id=course.id,
            status=CertificateStatus.PENDING,
        )
    )
    db.commit()

    assert client.get("/api/v1/certificates/pending").json()[0]["blockers"] == []
