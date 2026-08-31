"""Course / module / chapter domain service.

Split into focused sub-modules:

- ``_queries``    — read-side helpers (catalog, single course/module/chapter)
- ``_courses``    — course CRUD (create / update / soft-delete / restore / hard-delete)
- ``_modules``    — module CRUD
- ``_chapters``   — chapter CRUD
- ``_enrollment`` — student enrollment and progress sync
- ``_clone``      — deep course duplication

Everything is re-exported from this package so existing callers can keep
writing ``from app.services.course_service import <name>``.
"""

from ._chapters import create_chapter, delete_chapter, update_chapter
from ._clone import clone_course
from ._courses import (
    create_course,
    delete_course,
    permanently_delete_course,
    restore_course,
    update_course,
)
from ._enrollment import (
    enroll_user_in_course,
    get_user_courses,
    reading_progress_by_course,
    resync_course_progress,
    sync_enrollment_progress,
)
from ._modules import create_module, delete_module, update_module
from ._queries import get_chapter, get_course, get_courses, get_module, get_teacher_courses

__all__ = [
    "clone_course",
    "create_chapter",
    "create_course",
    "create_module",
    "delete_chapter",
    "delete_course",
    "delete_module",
    "enroll_user_in_course",
    "get_chapter",
    "get_course",
    "get_courses",
    "get_module",
    "get_teacher_courses",
    "get_user_courses",
    "permanently_delete_course",
    "reading_progress_by_course",
    "restore_course",
    "resync_course_progress",
    "sync_enrollment_progress",
    "update_chapter",
    "update_course",
    "update_module",
]
