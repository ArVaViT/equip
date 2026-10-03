"""The teacher's last mark on an assignment is the one that counts (2026-10-03).

Returned for revision with 40, resubmitted, marked 30: the student's item list
said 30 and the course grade used 40, because the calculator took MAX(grade)
over every submission.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.services.grade_calculator import calculate_all_student_grades, calculate_student_grade_for_course

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def test_a_resubmission_marked_lower_replaces_the_returned_mark(db: Session, teacher, student) -> None:
    course = Course(id="c-last-mark", status="published", created_by=teacher.id, quiz_weight=0, assignment_weight=100)
    db.add(course)
    module = Module(id="c-last-mark-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-last-mark-ch", module_id=module.id, order_index=0, chapter_type="assignment", title="E")
    db.add(chapter)
    db.flush()
    essay = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(essay)
    db.add(Enrollment(id="enr-c-last-mark", user_id=STUDENT_ID, course_id=course.id, progress=100))
    first = datetime.now(UTC) - timedelta(days=3)
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=essay.id,
            student_id=STUDENT_ID,
            status="returned",
            grade=40,
            submitted_at=first,
            graded_at=first + timedelta(hours=1),
        )
    )
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=essay.id,
            student_id=STUDENT_ID,
            status="graded",
            grade=30,
            submitted_at=first + timedelta(days=1),
            graded_at=first + timedelta(days=2),
        )
    )
    db.commit()

    assert calculate_student_grade_for_course(db, course, STUDENT_ID).assignment_avg == 30.0
    [row] = [r for r in calculate_all_student_grades(db, course) if str(r["student_id"]) == str(STUDENT_ID)]
    assert row["breakdown"].assignment_avg == 30.0
