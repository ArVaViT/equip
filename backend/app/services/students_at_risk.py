"""Students who are slipping away, for the teacher's home page.

Attrition in a free course is enormous and quiet: nobody announces they have
stopped. A call from the teacher in the second week saves a student; in the
fifth it is a formality. Two signals, both plain enough to act on:

* **quiet** — nothing at all for :data:`QUIET_AFTER` (seven days): no lesson
  read, no test started, no work handed in. Counted from enrolment for
  someone who never started, so a student who joined yesterday is not "quiet".
* **missed** — :data:`MISSED_DEADLINES` or more pieces of work past their due
  date with nothing handed in, not counting work the student was excused from
  or work that was due before they enrolled.

Nobody quiet for longer than :data:`GONE_AFTER` is listed: the list is for
the call that still helps.

Reading counts as activity here. The progress board's "last seen" counts only
tests and submissions, so a student reading every lesson looked gone; this
list would have sent a teacher to call the wrong people.

A handful of set-based queries for every course the teacher owns — no query
per student.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, CourseStatus
from app.models.enrollment import Enrollment
from app.models.grade_exemption import GradeExemption
from app.models.organization import STAFF_ROLES, MembershipStatus, OrganizationMember
from app.models.quiz import Quiz, QuizAttempt
from app.models.user import User, UserRole

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

QUIET_AFTER = timedelta(days=7)
MISSED_DEADLINES = 2
# Past a month of silence the call is a formality, and those students, having
# missed the most deadlines, would sit at the top for ever and push this
# week's quiet ones below the fold.
GONE_AFTER = timedelta(days=30)


@dataclass(frozen=True)
class AtRisk:
    student_id: str
    full_name: str
    #: For the teacher's "write to them" — the same address their gradebook shows.
    email: str | None
    course_id: str
    last_activity: datetime
    quiet_days: int
    missed_deadlines: int


def _aware(moment: datetime) -> datetime:
    """SQLite (the tests) hands back naive datetimes; every stored instant is UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def students_at_risk(db: Session, teacher_id: uuid.UUID, *, now: datetime | None = None) -> list[AtRisk]:
    """Everyone slipping in the teacher's published courses: most deadlines missed first, then quietest."""
    moment = now or datetime.now(UTC)
    course_ids = [
        c.id
        for c in db.query(Course.id).filter(
            Course.created_by == teacher_id,
            Course.status == CourseStatus.PUBLISHED,
            Course.deleted_at.is_(None),
        )
    ]
    if not course_ids:
        return []

    # Who is a student *here*: everyone enrolled who is not the author, not
    # platform staff, and not staff of the course's own organization. Until
    # 2026-10-03 this read ``User.role == 'student'``; with that column a
    # mirror of the highest membership held anywhere, a student of this
    # course who teaches in some other organization vanished from the list
    # — the teacher would have called everybody but them.
    staff_of_the_course_s_organization = (
        db.query(OrganizationMember.user_id)
        .join(Course, Course.organization_id == OrganizationMember.organization_id)
        .filter(
            Course.id == Enrollment.course_id,
            OrganizationMember.user_id == Enrollment.user_id,
            OrganizationMember.status == MembershipStatus.ACTIVE.value,
            OrganizationMember.role.in_(STAFF_ROLES),
        )
        .exists()
    )
    roster = (
        db.query(
            Enrollment.user_id,
            Enrollment.course_id,
            Enrollment.enrolled_at,
            User.full_name,
            User.email,
            Enrollment.progress,
        )
        .join(User, User.id == Enrollment.user_id)
        .filter(
            Enrollment.course_id.in_(course_ids),
            Enrollment.user_id != teacher_id,
            User.deactivated_at.is_(None),
            User.role != UserRole.ADMIN.value,
            ~staff_of_the_course_s_organization,
        )
        .all()
    )
    if not roster:
        return []
    # Taking a course again in a new cohort is a second enrolment row (ADR-010):
    # one person, one line, from the latest enrolment.
    latest: dict[tuple[str, str], Any] = {}
    for row in roster:
        key = (str(row[0]), row[1])
        kept = latest.get(key)
        if kept is None or (row[2] is not None and (kept[2] is None or _aware(row[2]) > _aware(kept[2]))):
            latest[key] = row
    # Finished is judged on that latest enrolment: someone who abandoned the
    # first run and completed the second is done, not slipping.
    roster = [row for row in latest.values() if row[5] < 100]

    last: dict[tuple[str, str], datetime] = {}

    def _note(rows: list) -> None:
        for user_id, course_id, at in rows:
            if at is None:
                continue
            key = (str(user_id), course_id)
            at = _aware(at)
            if key not in last or at > last[key]:
                last[key] = at

    _note(
        db.query(ChapterProgress.user_id, Chapter.course_id, func.max(ChapterProgress.completed_at))
        .join(Chapter, Chapter.id == ChapterProgress.chapter_id)
        .filter(Chapter.course_id.in_(course_ids))
        .group_by(ChapterProgress.user_id, Chapter.course_id)
        .all()
    )
    _note(
        db.query(
            QuizAttempt.user_id,
            Chapter.course_id,
            func.max(func.coalesce(QuizAttempt.completed_at, QuizAttempt.started_at)),
        )
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .filter(Chapter.course_id.in_(course_ids))
        .group_by(QuizAttempt.user_id, Chapter.course_id)
        .all()
    )
    _note(
        db.query(AssignmentSubmission.student_id, Chapter.course_id, func.max(AssignmentSubmission.submitted_at))
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .join(Chapter, Chapter.id == Assignment.chapter_id)
        .filter(Chapter.course_id.in_(course_ids))
        .group_by(AssignmentSubmission.student_id, Chapter.course_id)
        .all()
    )

    # Work past its due date, per course; then who handed it in, and who was excused.
    due = (
        db.query(Assignment.id, Chapter.course_id, Assignment.due_date)
        .join(Chapter, Chapter.id == Assignment.chapter_id)
        .filter(
            Chapter.course_id.in_(course_ids),
            Chapter.deleted_at.is_(None),
            Assignment.due_date.isnot(None),
            Assignment.due_date < moment,
        )
        .all()
    )
    due_by_course: dict[str, dict[str, datetime]] = defaultdict(dict)
    for assignment_id, course_id, due_date in due:
        due_by_course[course_id][str(assignment_id)] = _aware(due_date)
    handed_in = (
        {
            (str(student_id), str(assignment_id))
            for student_id, assignment_id in db.query(
                AssignmentSubmission.student_id, AssignmentSubmission.assignment_id
            )
            .filter(AssignmentSubmission.assignment_id.in_([a for a, _, _ in due]))
            .all()
        }
        if due
        else set()
    )
    excused = {
        (str(student_id), str(item_id))
        for student_id, item_id in db.query(GradeExemption.student_id, GradeExemption.item_id)
        .filter(GradeExemption.course_id.in_(course_ids), GradeExemption.item_type == "assignment")
        .all()
    }

    found: list[AtRisk] = []
    for user_id, course_id, enrolled_at, full_name, email, _progress in roster:
        student = str(user_id)
        # Nothing done yet: the clock runs from enrolment, so a student who
        # joined yesterday is not "quiet".
        seen = last.get((student, course_id))
        if seen is None and enrolled_at is not None:
            seen = _aware(enrolled_at)
        if seen is None:
            continue
        # Only deadlines that fell after the student joined: a late joiner is
        # not "missing" work that was due before they arrived (the tests
        # caught a student flagged on their second day).
        joined = _aware(enrolled_at) if enrolled_at is not None else None
        missed = sum(
            1
            for assignment_id, due_at in due_by_course.get(course_id, {}).items()
            if (joined is None or due_at > joined)
            and (student, assignment_id) not in handed_in
            and (student, assignment_id) not in excused
        )
        quiet = moment - seen
        if quiet > GONE_AFTER:
            continue
        if quiet >= QUIET_AFTER or missed >= MISSED_DEADLINES:
            found.append(
                AtRisk(
                    student_id=student,
                    full_name=full_name or email or student,
                    email=email or None,
                    course_id=course_id,
                    last_activity=seen,
                    quiet_days=quiet.days,
                    missed_deadlines=missed,
                )
            )
    found.sort(key=lambda r: (-r.missed_deadlines, r.last_activity))
    return found
