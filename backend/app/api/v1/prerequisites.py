from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_course_owner
from app.core.database import get_db
from app.models.course import Course, CourseStatus
from app.models.prerequisite import CoursePrerequisite
from app.models.user import User, UserRole
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.translation.resolve_for_display import (
    fetch_overlay_triples_bulk,
    pick_overlay_value,
)

router = APIRouter(prefix="/prerequisites", tags=["prerequisites"])


class PrerequisiteSetRequest(BaseModel):
    prerequisite_course_ids: list[str]


class PrerequisiteResponse(BaseModel):
    course_id: str
    prerequisite_course_id: str
    prerequisite_course_title: str | None = None


def _localized_title_map(
    db: Session,
    course_ids: list[str],
    *,
    display_locale: LocaleCode,
) -> dict[str, str]:
    """Return ``{course_id -> course title in display_locale}`` for live
    courses, falling back to the source title when no translation row
    exists. Uses the same overlay machinery as the catalog endpoint so
    behaviour stays identical to ``GET /courses``.
    """
    if not course_ids:
        return {}
    rows = (
        db.query(Course.id, Course.title, Course.source_locale)
        .filter(Course.id.in_(course_ids), Course.deleted_at.is_(None))
        .all()
    )
    specs = [("course", str(cid), "title") for cid, _, _ in rows]
    overlay = fetch_overlay_triples_bulk(db, specs, display_locale)
    out: dict[str, str] = {}
    for cid, source_title, source_locale in rows:
        out[str(cid)] = (
            pick_overlay_value(
                overlay,
                "course",
                str(cid),
                "title",
                source_title,
                source_locale=normalize_locale(source_locale),
                display_locale=display_locale,
            )
            or source_title
        )
    return out


@router.get("/course/{course_id}", response_model=list[PrerequisiteResponse])
def get_prerequisites(
    response: Response,
    course_id: str,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Vary"] = "Accept-Language"
    # Requires auth and that the course is visible to the caller. Previously
    # this endpoint was public and would happily leak draft-course
    # relationships to anonymous callers (audit P1.4). Trashed courses are
    # treated as not found so deleted prerequisites don't leak either.
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    is_admin = current_user.role == UserRole.ADMIN.value
    is_owner = str(course.created_by) == str(current_user.id)
    is_published = getattr(course, "status", None) == CourseStatus.PUBLISHED
    if not (is_admin or is_owner or is_published):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    prereqs = db.query(CoursePrerequisite).filter(CoursePrerequisite.course_id == course_id).all()
    prereq_ids = [p.prerequisite_course_id for p in prereqs]
    display_locale: LocaleCode = normalize_locale(accept_language)
    title_map = _localized_title_map(db, prereq_ids, display_locale=display_locale)

    return [
        PrerequisiteResponse(
            course_id=p.course_id,
            prerequisite_course_id=p.prerequisite_course_id,
            prerequisite_course_title=title_map.get(p.prerequisite_course_id),
        )
        for p in prereqs
    ]


@router.put("/course/{course_id}", response_model=list[PrerequisiteResponse])
def set_prerequisites(
    course_id: str,
    data: PrerequisiteSetRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    verify_course_owner(db, course_id, teacher)

    # Dedupe while preserving the order the teacher submitted. Without this
    # a client that accidentally sent the same prerequisite twice would
    # insert duplicate rows with the same ``(course_id, prereq_id)`` pair,
    # tripping the composite PK on commit and surfacing as a generic 409.
    prereq_ids: list[str] = list(dict.fromkeys(data.prerequisite_course_ids))

    # Prevent self-cycle (A -> A) up front -- the multi-node check below
    # would catch this too, but the targeted error message is friendlier.
    if course_id in prereq_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A course cannot be its own prerequisite",
        )

    if prereq_ids:
        # Require every prerequisite to be a live (non-trashed) course so
        # teachers can't wire deleted content back into an active course.
        existing_courses = db.query(Course).filter(Course.id.in_(prereq_ids), Course.deleted_at.is_(None)).all()
        existing_ids = {str(c.id) for c in existing_courses}
        for pid in prereq_ids:
            if pid not in existing_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Prerequisite course '{pid}' not found",
                )

        # Multi-node cycle detection. Without this a teacher can wire
        # A -> B and B -> A and any consumer that walks the prerequisite
        # DAG (course-gate UI, topological-sort export) loops forever.
        # Edge semantics: ``course_id -> prereq_id`` means
        # "course_id requires prereq_id". A new edge ``course_id -> pid``
        # closes a cycle iff there's already a path pid -> ... -> course_id
        # (i.e. pid already transitively requires course_id, so adding
        # course_id -> pid would loop back). We DFS forward through the
        # existing "requires" edges starting at each proposed pid; if we
        # ever land on course_id, reject.
        existing_edges = db.query(
            CoursePrerequisite.course_id,
            CoursePrerequisite.prerequisite_course_id,
        ).all()
        # requires[X] = {courses that X currently requires}
        requires: dict[str, set[str]] = {}
        for src, dst in existing_edges:
            requires.setdefault(str(src), set()).add(str(dst))

        for pid in prereq_ids:
            stack = [pid]
            visited: set[str] = set()
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)
                if node == course_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Adding '{pid}' as a prerequisite would create a "
                            "circular dependency with the course's existing prerequisite chain."
                        ),
                    )
                stack.extend(requires.get(node, set()) - visited)

    db.query(CoursePrerequisite).filter(CoursePrerequisite.course_id == course_id).delete()

    new_prereqs = []
    for pid in prereq_ids:
        prereq = CoursePrerequisite(course_id=course_id, prerequisite_course_id=pid)
        db.add(prereq)
        new_prereqs.append(prereq)

    db.commit()

    prereq_ids = [p.prerequisite_course_id for p in new_prereqs]
    prereq_courses = db.query(Course).filter(Course.id.in_(prereq_ids)).all() if prereq_ids else []
    title_map = {str(c.id): c.title for c in prereq_courses}

    return [
        PrerequisiteResponse(
            course_id=p.course_id,
            prerequisite_course_id=p.prerequisite_course_id,
            prerequisite_course_title=title_map.get(p.prerequisite_course_id),
        )
        for p in new_prereqs
    ]
