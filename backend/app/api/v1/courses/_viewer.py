"""What a course response says about its reader: may they edit it, and who wrote it.

Shared by the course page (``catalog``) and the write routes (``crud``) so
that every ``CourseResponse`` answers the same way. A separate module
because both of those register routes on the shared router at import
time, and one importing the other would change the order the routes are
registered in.
"""

from app.api.dependencies import is_owner_or_admin
from app.models.course import Course
from app.models.user import User
from app.schemas.course import CourseResponse


def for_viewer(out: CourseResponse, course: Course, viewer: User | None) -> CourseResponse:
    """Say whether this reader may edit the course, and name the author only to them.

    The client decided ownership by comparing its own id with ``created_by``,
    so the author's account id went to every guest who opened a course page.
    The server already knows the answer (``is_owner_or_admin`` gates the
    source text and the unreleased lessons on it); now it says so, and a
    reader who may not edit is not told who may.
    """
    out.viewer_can_edit = is_owner_or_admin(course, viewer)
    if not out.viewer_can_edit:
        out.created_by = None
    return out


def as_seen_by(course: Course, viewer: User | None) -> CourseResponse:
    """``course`` serialised for ``viewer`` — the write routes' one-liner."""
    return for_viewer(CourseResponse.model_validate(course, from_attributes=True), course, viewer)
