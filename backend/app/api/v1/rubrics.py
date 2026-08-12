"""Rubrics: defining a marking standard, and marking against it.

Design: `assessment-integrity-and-the-graders-day.md` §6.3.

Two things here deserve to be read before the code.

**A partially marked essay is not a graded essay.** Saving marks is
incremental — a teacher works down the criteria, and the queue autosaves — but
the submission only becomes `graded`, with the number and the notification that
follow, once every live criterion has a decision on it. Publishing a half-filled
grid as a mark would tell a student they scored 40% when the teacher had simply
not reached the third criterion yet.

**Every id in the request is checked against the assignment's own rubric.** A
level belongs to a criterion, a criterion belongs to the rubric, and the rubric
belongs to the assignment. Without that chain a teacher could post a level id
from any rubric on the platform and give an arbitrary number of points — and it
would look like a normal mark in every record afterwards.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_chapter_owner
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.rubric import AssignmentRubric, Rubric, RubricCriterion, RubricLevel, RubricMark
from app.models.user import User
from app.schemas.rubric import (
    RubricCreate,
    RubricMarksRequest,
    RubricResponse,
    SubmissionRubricResponse,
)
from app.services import rubric_service
from app.services.audit_service import log_action
from app.services.domain_access import resolve_chapter_course_id
from app.services.submission_grading import apply_grade

router = APIRouter(prefix="/rubrics", tags=["rubrics"])


def _course_of_assignment(db: Session, assignment: Assignment) -> str:
    return resolve_chapter_course_id(db, assignment.chapter_id)


def _get_assignment_or_404(db: Session, assignment_id: UUID) -> Assignment:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Assignment not found",
            context={"resource_type": "assignment", "assignment_id": str(assignment_id)},
        )
    return assignment


@router.post("", response_model=RubricResponse, status_code=status.HTTP_201_CREATED)
def create_rubric(
    data: RubricCreate,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Create a rubric with its criteria and levels in one call.

    One call rather than three endpoints and a client-side transaction: a
    rubric that exists with two of its four criteria is a marking standard
    nobody agreed to, and it would be the state left behind by every failed
    save.
    """
    from app.api.dependencies import verify_course_owner

    verify_course_owner(db, data.course_id, teacher)

    rubric = Rubric(course_id=data.course_id, title=data.title, created_by=teacher.id)
    db.add(rubric)
    db.flush()

    for c_index, criterion_in in enumerate(data.criteria):
        criterion = RubricCriterion(
            rubric_id=rubric.id,
            title=criterion_in.title,
            description=criterion_in.description,
            order_index=c_index,
        )
        db.add(criterion)
        db.flush()
        for l_index, level_in in enumerate(criterion_in.levels):
            db.add(
                RubricLevel(
                    criterion_id=criterion.id,
                    label=level_in.label,
                    points=level_in.points,
                    description=level_in.description,
                    order_index=l_index,
                )
            )
    db.commit()
    log_action(
        db,
        teacher.id,
        "rubric_created",
        "rubric",
        str(rubric.id),
        details={"course_id": data.course_id, "criteria": len(data.criteria)},
        request=request,
    )
    db.refresh(rubric)
    return rubric_service.rubric_payload(db, rubric)


@router.get("", response_model=list[RubricResponse])
def list_rubrics(
    course_id: str = Query(..., max_length=36),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """The course's marking standards, so a teacher reuses rather than retypes."""
    from app.api.dependencies import verify_course_owner

    verify_course_owner(db, course_id, teacher)
    rubrics = (
        db.query(Rubric)
        .filter(Rubric.course_id == course_id, Rubric.archived_at.is_(None))
        .order_by(Rubric.created_at.desc())
        .all()
    )
    return [rubric_service.rubric_payload(db, r) for r in rubrics]


@router.post("/attach/{assignment_id}", response_model=RubricResponse)
def attach_rubric(
    assignment_id: UUID,
    rubric_id: UUID = Query(...),
    request: Request = None,  # type: ignore[assignment]
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Mark this assignment by this rubric, and make its total the maximum.

    The maximum moves because there cannot be two of them. An assignment out of
    100 marked by a rubric adding to 40 gives every student 40% of what they
    earned, and every number downstream looks arithmetically correct.
    """
    assignment = _get_assignment_or_404(db, assignment_id)
    verify_chapter_owner(db, assignment.chapter_id, teacher)

    rubric = db.query(Rubric).filter(Rubric.id == rubric_id, Rubric.archived_at.is_(None)).first()
    if rubric is None or rubric.course_id != _course_of_assignment(db, assignment):
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="That rubric belongs to a different course",
            context={"resource_type": "rubric", "rubric_id": str(rubric_id)},
        )

    existing = db.query(AssignmentRubric).filter(AssignmentRubric.assignment_id == assignment_id).first()
    if existing is not None:
        existing.rubric_id = rubric_id
        existing.attached_by = teacher.id
    else:
        db.add(AssignmentRubric(assignment_id=assignment_id, rubric_id=rubric_id, attached_by=teacher.id))

    rubric_service.sync_assignment_max_score(db, assignment_id, rubric_id)
    db.commit()
    log_action(
        db,
        teacher.id,
        "rubric_attached",
        "assignment",
        str(assignment_id),
        details={"rubric_id": str(rubric_id), "max_score": assignment.max_score},
        request=request,
    )
    return rubric_service.rubric_payload(db, rubric)


@router.get("/submission/{submission_id}", response_model=SubmissionRubricResponse)
def read_submission_rubric(
    submission_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The grid and what was chosen on it — for the teacher, and for its author.

    A rubric shown only to the person marking is a private opinion with
    arithmetic on it. The student sees the same criteria and the same levels,
    with their own marked.
    """
    submission = db.query(AssignmentSubmission).filter(AssignmentSubmission.id == submission_id).first()
    if not submission:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Submission not found",
            context={"resource_type": "submission", "resource_id": str(submission_id)},
        )
    assignment = _get_assignment_or_404(db, submission.assignment_id)

    if submission.student_id != current_user.id:
        # Not their own work: only the teacher who owns the chapter may read it.
        verify_chapter_owner(db, assignment.chapter_id, current_user)

    rubric = rubric_service.rubric_for_assignment(db, assignment.id)
    if rubric is None:
        return {"rubric": None, "marks": [], "earned": None, "out_of": None}

    earned, out_of = rubric_service.score_from_marks(db, submission_id)
    return {
        "rubric": rubric_service.rubric_payload(db, rubric),
        "marks": rubric_service.marks_payload(db, submission_id),
        "earned": earned,
        "out_of": out_of,
    }


@router.put("/submission/{submission_id}/marks", response_model=SubmissionRubricResponse)
def set_submission_marks(
    submission_id: UUID,
    data: RubricMarksRequest,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Record the levels chosen, and grade the work once the grid is complete."""
    submission = db.query(AssignmentSubmission).filter(AssignmentSubmission.id == submission_id).first()
    if not submission:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Submission not found",
            context={"resource_type": "submission", "resource_id": str(submission_id)},
        )
    assignment = _get_assignment_or_404(db, submission.assignment_id)
    verify_chapter_owner(db, assignment.chapter_id, teacher)

    rubric = rubric_service.rubric_for_assignment(db, assignment.id)
    if rubric is None:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="This assignment is not marked by a rubric",
            context={"resource_type": "assignment", "assignment_id": str(assignment.id)},
        )

    criteria = {c.id: c for c in rubric_service.live_criteria(db, rubric.id)}
    levels_by_criterion = rubric_service.live_levels(db, list(criteria))
    valid_levels = {lvl.id: c_id for c_id, levels in levels_by_criterion.items() for lvl in levels}

    for mark in data.marks:
        # The chain: this level belongs to this criterion, and this criterion
        # belongs to the rubric this assignment is marked by. Without it, a
        # level id from any rubric on the platform buys arbitrary points, and
        # the result looks like an ordinary mark in every record afterwards.
        if mark.criterion_id not in criteria or valid_levels.get(mark.level_id) != mark.criterion_id:
            raise equip_error(
                ErrorCode.VALIDATION_FAILED,
                status_code=status.HTTP_400_BAD_REQUEST,
                message="That level does not belong to this assignment's rubric",
                context={
                    "resource_type": "rubric",
                    "criterion_id": str(mark.criterion_id),
                    "level_id": str(mark.level_id),
                },
            )

    existing = {m.criterion_id: m for m in db.query(RubricMark).filter(RubricMark.submission_id == submission_id).all()}
    for mark in data.marks:
        row = existing.get(mark.criterion_id)
        if row is None:
            db.add(
                RubricMark(
                    submission_id=submission_id,
                    criterion_id=mark.criterion_id,
                    level_id=mark.level_id,
                    comment=mark.comment,
                    marked_by=teacher.id,
                )
            )
        else:
            row.level_id = mark.level_id
            row.comment = mark.comment
            row.marked_by = teacher.id
    db.flush()

    marked_criteria = {
        m.criterion_id for m in db.query(RubricMark).filter(RubricMark.submission_id == submission_id).all()
    }
    complete = bool(criteria) and marked_criteria >= set(criteria)
    earned, out_of = rubric_service.score_from_marks(db, submission_id)

    if complete:
        from app.api.v1.assignments import _course_source_locale_for_chapter

        apply_grade(
            db,
            submission=submission,
            assignment=assignment,
            grade=earned,
            feedback=data.feedback if data.feedback is not None else submission.feedback,
            new_status="graded",
            teacher_id=teacher.id,
            source_locale=_course_source_locale_for_chapter(db, assignment.chapter_id),
            request=request,
            source="rubric",
        )
    else:
        # Incremental marking. The work keeps waiting on the teacher, and no
        # number reaches the student — a half-filled grid published as a mark
        # says 40% when the third criterion simply has not been reached.
        db.commit()

    return {
        "rubric": rubric_service.rubric_payload(db, rubric),
        "marks": rubric_service.marks_payload(db, submission_id),
        "earned": earned,
        "out_of": out_of,
    }
