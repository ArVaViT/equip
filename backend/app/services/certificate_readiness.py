"""Why this student cannot have a certificate yet — in specifics, not a "no".

Today the certificate button either works or refuses with a sentence about
progress. Under the D9 gate it will refuse far more often and for reasons a
student cannot see: two essays nobody has marked, an итоговая of 64 against a
pass line of 70, one assignment sent back for revision. A refusal a student
cannot act on turns into a message to the teacher, and a teacher who gets that
message five times a week starts approving certificates to make it stop.

So the explanation ships **before** the enforcement (Принцип 2). This module is
the shared answer: the same list renders next to the student's certificate
button and on the teacher's pending-certificates card, and — in the final PR of
this phase — is what the gate itself refuses on. One computation, so the reason
shown can never differ from the reason applied.

**Codes, not sentences.** Every blocker is a code plus numbers plus the chapters
it points at. The words live in the frontend catalogues, in every locale the
platform speaks. A reason list assembled in Russian in the backend would have to
be reassembled for each language added, and the wording would drift between the
student's screen and the teacher's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.models.quiz import QuizAnswer, QuizAttempt, QuizQuestion
from app.services.gradable_items import course_items
from app.services.grade_calculator import calculate_student_grade_for_course
from app.services.grade_exemption_service import excused_item_ids
from app.services.grade_override import resolve_official_row
from app.services.grade_sheet_service import FAIL, NOT_ATTESTED, official_result
from app.services.grading_queue import unread_answer_filters
from app.services.grading_scheme import effective_bands, get_org_settings
from app.services.zachet import NOT_ATTESTED as ZACHET_NOT_ATTESTED
from app.services.zachet import (
    latest_submissions,
    unpassed_quizzes,
    zachet_result,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.models.course import Course
    from app.models.enrollment import Enrollment

#: The course is not finished. Everything else is beside the point until it is.
COURSE_NOT_COMPLETE = "course_not_complete"
#: Work handed in that nobody has marked. The student cannot do anything about
#: this one, and that is exactly why it must be named — otherwise the refusal
#: reads as their fault.
WORK_NOT_GRADED = "work_not_graded"
#: Handed back for revision. This one *is* their move.
WORK_RETURNED = "work_returned"
#: Never handed in.
WORK_NOT_SUBMITTED = "work_not_submitted"
#: The number is below the pass line.
BELOW_THRESHOLD = "below_threshold"
#: pass/fail course: a quiz not passed at its own passing score (D2).
QUIZZES_NOT_PASSED = "quizzes_not_passed"
#: Nothing was assessed and nobody has decided — a teacher has to set a grade.
NOT_ASSESSED = "not_assessed"

#: The blockers a student cannot clear on their own, and therefore the only
#: ones a пересдача request means anything for (D12).
#:
#: Unmarked work is not here: the answer to "nobody has read my essay" is to
#: wait, and a request button next to it invites a student to chase a teacher
#: for something already in their queue. Work never handed in is not here
#: either — the student can simply hand it in.
RETAKE_ACTIONABLE = frozenset({QUIZZES_NOT_PASSED, BELOW_THRESHOLD, NOT_ASSESSED})

#: The notification a пересдача request raises, and how long the same student
#: asking again folds into the existing one instead of adding another.
RETAKE_REQUEST_NOTIFICATION = "retake_requested"
RETAKE_REQUEST_COOLDOWN_HOURS = 24


@dataclass(frozen=True)
class Blocker:
    """One reason, with everything a screen needs to make it actionable."""

    code: str
    #: Numbers only. No words: see the module docstring.
    params: dict[str, Any] = field(default_factory=dict)
    #: The chapters this points at, so the surface can link to the actual work
    #: rather than tell someone to go looking for it.
    chapter_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "params": self.params, "chapter_ids": self.chapter_ids}


def certificate_blockers(
    db: Session,
    course: Course,
    enrollment: Enrollment,
    student_id: UUID,
    *,
    breakdown: Any = None,
    zachet: str | None = None,
) -> list[Blocker]:
    """Everything standing between this student and a certificate. Empty = ready.

    Ordered the way a person reads it: what stops it outright first, then what
    is waiting on the teacher, then what is waiting on the student, then the
    number. A list that opens with «64% < 70%» when four essays are unmarked
    tells the student a falsehood about their standing.
    """
    quizzes, assignments = course_items(db, course.id)
    # Both are handed in by the student's own grade view, which has just
    # computed them. Recomputing on the hottest authenticated page in the
    # product would double its query count for an identical answer.
    if breakdown is None:
        breakdown = calculate_student_grade_for_course(db, course, student_id)
    scheme = course.grading_scheme
    threshold = Decimal(str(course.pass_threshold))

    if scheme == "pass_fail" and zachet is None:
        zachet, _owed = zachet_result(
            db,
            student_id=student_id,
            course_id=course.id,
            progress=enrollment.progress,
            all_items_excused=breakdown.result_state == "not_assessed",
        )

    official_row = resolve_official_row(db, student_id=student_id, course_id=course.id)
    state, _code, _score, is_override = official_result(
        breakdown,
        official_row.override_code if official_row is not None else None,
        official_row.override_score if official_row is not None else None,
        scheme=scheme,
        pass_threshold=threshold,
        bands=effective_bands(get_org_settings(db, course.organization_id), scheme),
        zachet=zachet,
    )

    # A hand-set passing grade is a decision a teacher already made, with the
    # whole picture in front of them (D7). It ends the conversation — listing
    # ungraded work under it would invite somebody to undo that decision.
    if is_override and state not in {FAIL, NOT_ATTESTED}:
        return []

    blockers: list[Blocker] = []

    if enrollment.progress < 100:
        blockers.append(Blocker(COURSE_NOT_COMPLETE, {"progress": int(enrollment.progress)}))

    # Every id is compared as a string. The two sources disagree on type —
    # ``zachet`` returns strings, the ORM rows hand back UUIDs — and a set
    # difference between the two silently subtracts nothing, which would have
    # shown the same essay twice under two different headings.
    excused_quiz_ids, excused_assignment_ids = excused_item_ids(db, student_id=student_id, course_id=course.id)
    excused = {str(i) for i in excused_quiz_ids} | {str(i) for i in excused_assignment_ids}
    chapter_of = {str(i.id): str(i.chapter_id) for i in (*quizzes, *assignments) if i.chapter_id}

    # Waiting on the teacher, waiting on the student, and never handed in read
    # identically as "not done" and are three different conversations.
    awaiting_marking = {str(q) for q in _quizzes_awaiting_marking(db, student_id, [q.id for q in quizzes])}
    submissions = latest_submissions(db, student_id=student_id, assignment_ids=[a.id for a in assignments])
    returned: set[str] = set()
    missing: set[str] = set()
    for assignment in assignments:
        aid = str(assignment.id)
        if aid in excused:
            continue
        submission = submissions.get(assignment.id)
        if submission is None:
            missing.add(aid)
        elif submission["status"] == "returned":
            returned.add(aid)
        elif submission["status"] == "submitted" and submission["grade"] is None:
            awaiting_marking.add(aid)
    # A quiz never attempted counts as a zero in a band scheme and as unmet in
    # pass/fail — either way it belongs on the list by name, not as a number.
    attempted = _quizzes_attempted(db, student_id, [q.id for q in quizzes])
    missing |= {str(q.id) for q in quizzes if str(q.id) not in excused and q.id not in attempted}

    awaiting_marking -= excused

    for code, ids in ((WORK_NOT_GRADED, awaiting_marking), (WORK_RETURNED, returned), (WORK_NOT_SUBMITTED, missing)):
        if ids:
            blockers.append(Blocker(code, {"count": len(ids)}, sorted({chapter_of[i] for i in ids if i in chapter_of})))

    if scheme == "pass_fail":
        if zachet == ZACHET_NOT_ATTESTED:
            blockers.append(Blocker(NOT_ASSESSED))
            return blockers
        # A quiz that was attempted and failed is neither missing nor unmarked:
        # the student has to sit it again, which is a different instruction.
        failed = set(unpassed_quizzes(db, student_id=student_id, course_id=course.id)) - awaiting_marking - missing
        if failed:
            blockers.append(
                Blocker(
                    QUIZZES_NOT_PASSED,
                    {"count": len(failed)},
                    sorted({chapter_of[i] for i in failed if i in chapter_of}),
                )
            )
        return blockers

    if state == NOT_ATTESTED:
        # "Not attested" covers two situations that need opposite sentences.
        # Nothing has been marked *yet* — already listed above, item by item,
        # and the answer is to wait. Or nothing is left to mark at all, and a
        # teacher has to decide by hand. Only the second is this blocker; the
        # first was already fully explained, and adding "your teacher must set
        # a grade" under it sends a student to ask for something that would
        # arrive on its own.
        if not blockers:
            blockers.append(Blocker(NOT_ASSESSED))
        return blockers

    if state == FAIL:
        # The number goes last, and it says so when it is not yet a verdict.
        # Итоговая counts unmarked work as zero, so while anything is unread the
        # figure is a floor that can only rise. «64% < 70%» presented flatly next
        # to two unread essays tells a student their standing is worse than
        # anybody yet knows — and `provisional` is a flag rather than something
        # the surface has to infer by cross-referencing the other blockers,
        # because that inference is exactly what a second surface forgets.
        blockers.append(
            Blocker(
                BELOW_THRESHOLD,
                {
                    "final_score": round(float(breakdown.final_score), 2),
                    "pass_threshold": float(threshold),
                    "provisional": bool(awaiting_marking),
                },
            )
        )

    return blockers


def _quizzes_attempted(db: Session, student_id: UUID, quiz_ids: list) -> set:
    """Quizzes this student has finished at least once."""
    if not quiz_ids:
        return set()
    rows = (
        db.query(QuizAttempt.quiz_id)
        .filter(
            QuizAttempt.quiz_id.in_(quiz_ids),
            QuizAttempt.user_id == student_id,
            QuizAttempt.completed_at.isnot(None),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _quizzes_awaiting_marking(db: Session, student_id: UUID, quiz_ids: list) -> set:
    """Quizzes where this student has a finished attempt with an unread answer.

    One query for the course, not one per quiz: this runs on the student's own
    course page, which is the most-loaded authenticated screen there is.
    """
    if not quiz_ids:
        return set()
    rows = (
        db.query(QuizAttempt.quiz_id)
        .join(QuizAnswer, QuizAnswer.attempt_id == QuizAttempt.id)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .filter(
            QuizAttempt.quiz_id.in_(quiz_ids),
            QuizAttempt.user_id == student_id,
            # The same definition the teacher's queue uses. Told "your essay is
            # not marked yet" for an answer that is not on the teacher's list,
            # a student waits for something that will never arrive.
            *unread_answer_filters(),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def retake_would_help(blockers: list[Blocker]) -> bool:
    """Whether «запросить пересдачу» means anything for this student (D12).

    Only for what they cannot clear alone, and only once the obstacle is real.
    A score below the line while work is still unread is provisional — it
    counts every unmarked essay as a zero and can only rise — so a request
    raised against it asks a teacher to fix a number that is not yet their
    verdict. That is a student chasing their own unread homework.
    """
    return any(b.code in RETAKE_ACTIONABLE and not b.params.get("provisional") for b in blockers)
