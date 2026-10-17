"""``PUT /courses/{id}/outline`` — the teacher's order, in one write.

The editor used to reorder a course with one request per row it
renumbered — modules through ``PUT .../modules/{id}``, lessons through
``PUT .../chapters/{id}`` — and the two families numbered things in two
spaces that nothing reconciled. Half a reorder could land, and a module
moved without its lessons being renumbered could leave a loose lesson on
the wrong side of it.

Now the editor sends the course as it should read and the server writes
it in one transaction (``course_service._outline.write_outline``). A
screen that is out of date — a lesson added in another tab, one deleted
meanwhile — sends an outline that does not name exactly the live rows;
that is refused with 409 and nothing is written, and the editor reloads.

Structure only: no text changes, so nothing here has a translation to
reconcile.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_teacher, verify_course_owner
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.user import User
from app.schemas.course import CourseOutlineUpdate
from app.services.course_service._outline import OutlineMismatchError, OutlinePlaceError, write_outline

from ._router import router


def outline_place_conflict(exc: OutlinePlaceError, course_id: str) -> HTTPException:
    """409 for a place in the shared sequence sent to a one-row route
    (see ``OutlinePlaceError``). Nothing was written: the services raise
    before touching the row. A client that gets it reloads the course."""
    return equip_error(
        ErrorCode.VALIDATION_FAILED,
        status_code=status.HTTP_409_CONFLICT,
        message=str(exc),
        context={"course_id": course_id},
    )


@router.put("/{course_id}/outline", status_code=status.HTTP_204_NO_CONTENT)
def save_course_outline(
    course_id: str,
    data: CourseOutlineUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    verify_course_owner(db, course_id, teacher.id)
    try:
        write_outline(db, course_id, [(p.module_id, p.chapter_ids) for p in data.places])
    except OutlineMismatchError as exc:
        db.rollback()
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=str(exc),
            context={"course_id": course_id},
        ) from exc
    db.commit()
