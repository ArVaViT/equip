"""Course-level write endpoints: create / update / delete / clone / restore."""

import logging

from fastapi import Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import assert_course_owner, organization_of, require_teacher
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.sanitize import sanitize_string
from app.models.course import Course, CourseStatus
from app.models.user import User, UserRole
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate
from app.services.audit_service import log_action
from app.services.course_service import (
    clone_course,
    create_course,
    delete_course,
    get_course,
    permanently_delete_course,
    restore_course,
    update_course,
)
from app.services.staged_edits import promote_staged_entity_unconditionally
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.pipeline_hooks import (
    run_course_translation_pipeline_if_published,
)
from app.services.translation.resolve_for_display import populate_spine_texts

from ._router import router

logger = logging.getLogger(__name__)


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_new_course(
    data: CourseCreate,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Course:
    # Anti-abuse cap (pilot hygiene): one teacher hoarding hundreds of
    # courses is either a runaway script or a misunderstanding — either way
    # a human conversation, not more rows. Admins are exempt (they seed and
    # migrate content). Soft-deleted courses don't count — trash-then-create
    # must not dead-end a legitimate teacher.
    if teacher.role != UserRole.ADMIN.value:
        live_count = db.query(Course).filter(Course.created_by == teacher.id, Course.deleted_at.is_(None)).count()
        if live_count >= settings.MAX_COURSES_PER_TEACHER:
            raise equip_error(
                ErrorCode.VALIDATION_FAILED,
                status_code=status.HTTP_400_BAD_REQUEST,
                message=(
                    f"Course limit reached ({settings.MAX_COURSES_PER_TEACHER}). "
                    "Contact an administrator if you need more."
                ),
                context={
                    "resource_type": "course",
                    "limit": settings.MAX_COURSES_PER_TEACHER,
                    "current": live_count,
                },
            )

    if data.title:
        data.title = sanitize_string(data.title)
    # The teacher writes in their UI language by definition — derive the
    # course's source_locale from their profile so they never have to pick
    # it manually, and so RU↔EN translation is symmetric (a teacher who
    # works in EN gets RU translations for their RU students; vice versa
    # for an RU-authoring teacher). ``preferred_locale`` is itself
    # CHECK-constrained to the supported locale set.
    course = create_course(
        db,
        data,
        teacher.id,
        organization_id=organization_of(teacher),
        source_locale=teacher.preferred_locale,
    )
    log_action(db, teacher.id, "create", "course", course.id, request=request)
    return course


@router.put("/{course_id}", response_model=CourseResponse)
def update_existing_course(
    course_id: str,
    data: CourseUpdate,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Course:
    course = get_course(db, course_id)
    if not course:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    assert_course_owner(course, teacher)
    # ``access_mode`` (public vs institute) controls solo-enrollment
    # access per ADR-010. Letting any course owner flip it would let a
    # teacher promote their institute course to public, bypassing the
    # invitation-only gate. Restrict the field to admins.
    if data.access_mode is not None and teacher.role != UserRole.ADMIN.value:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only admins can change course access mode",
            context={"resource_type": "course", "course_id": course_id, "field": "access_mode"},
        )
    if data.title:
        data.title = sanitize_string(data.title)
    old_status = course.status
    result = update_course(db, course, data)
    details: dict[str, object] = {}
    if data.status and data.status != old_status:
        details = {"old_status": old_status, "new_status": data.status}
    # Special-case draft→published so the audit log distinguishes a
    # publication event from a generic update.
    is_publish_event = data.status == CourseStatus.PUBLISHED and old_status != CourseStatus.PUBLISHED

    # Publication is a state the course reaches, not a button that
    # fires. A course going out for the first time only enters the
    # catalog once every language has it and every translation has
    # passed its check; until then it sits in ``publishing``, which
    # every reader treats as unpublished. The worker promotes it.
    #
    # This applies to the first publication only. An already-published
    # course whose teacher fixes a typo is NOT pulled back — that would
    # take a live course away from every student in every language
    # until the machine caught up. Their text is replaced field by
    # field as each translation passes.
    if is_publish_event:
        completeness = course_translation_completeness(db, result)
        if not completeness.is_complete:
            result.status = CourseStatus.PUBLISHING
            db.flush()
            details["new_status"] = CourseStatus.PUBLISHING.value
            details["translations_ready"] = f"{completeness.present}/{completeness.required}"

    # Coming back off the catalog: edits that were being held for the
    # sake of students now have no students to be held from, and leaving
    # them in the staging table would hide the teacher's own work from
    # their own draft. Release them as they are — half-translated
    # fields simply mean the publication gate will keep the course in
    # ``publishing`` until the pipeline finishes, which is exactly what
    # that gate is for.
    left_publication = old_status == CourseStatus.PUBLISHED and result.status != CourseStatus.PUBLISHED
    if left_publication:
        released = promote_staged_entity_unconditionally(db, course_id=str(course_id))
        if released:
            details["released_held_edits"] = released

    action = "publish" if is_publish_event else "update"
    log_action(db, teacher.id, action, "course", course_id, details=details or None, request=request)

    # Full-course translation when published (initial publish or edits
    # while live). This goes through the pipeline hook rather than
    # calling the orchestrator directly, so it honours
    # ``TRANSLATION_QUEUE_ENABLED``: one INSERT into ``translation_jobs``
    # and the cron worker drains it out of band.
    #
    # It used to call ``translate_course_content`` from inside the
    # request. On a course of any size that is a Gemini round-trip per
    # field, in series, while the teacher's browser waits — and past 300
    # seconds Vercel returns 504 to a teacher whose save had in fact
    # succeeded. Worse, with the queue enabled in production the same
    # work was ALSO being enqueued by the entity hooks, so the slow path
    # was buying nothing.
    #
    # Failures still never block the save; the hook logs and swallows.
    run_course_translation_pipeline_if_published(db, str(course_id))

    # Re-hydrate spine texts here: ``translate_course_content`` and the
    # audit log writes both commit, expiring SQLAlchemy's attribute cache
    # and re-loading modules as plain ORM instances with no runtime title.
    # Without this, response serialisation fails Pydantic validation.
    populate_spine_texts(db, [result])
    return result


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_course(
    course_id: str,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    course = get_course(db, course_id)
    if not course:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    assert_course_owner(course, teacher)
    # ``course.title`` is a runtime attribute hydrated by
    # ``populate_spine_texts``. ``get_course`` does NOT hydrate, so the
    # log_action below would stamp ``None`` into the audit row without
    # this call. The cost is one indexed cv lookup per delete.
    populate_spine_texts(db, [course])
    log_action(db, teacher.id, "delete", "course", course_id, details={"title": course.title}, request=request)
    delete_course(db, course)


@router.post(
    "/{course_id}/clone",
    response_model=CourseResponse,
    status_code=status.HTTP_201_CREATED,
)
def clone_existing_course(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Course:
    course = get_course(db, course_id)
    if not course:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    # Drafts are only visible (and therefore clonable) to their owner,
    # regardless of admin status.
    is_owner = str(course.created_by) == str(teacher.id)
    if course.status != CourseStatus.PUBLISHED and not is_owner:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only the owner can clone a draft course",
            context={"resource_type": "course", "course_id": course_id},
        )
    new_course = clone_course(db, course_id, str(teacher.id))
    if not new_course:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to clone course",
            context={"resource_type": "course", "course_id": course_id},
        )
    return new_course


@router.post("/{course_id}/restore", response_model=CourseResponse)
def restore_deleted_course(
    course_id: str,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Course:
    course = get_course(db, course_id, include_deleted=True)
    if not course:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Course not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    if course.deleted_at is None:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Course is not deleted",
            context={"resource_type": "course", "course_id": course_id},
        )
    assert_course_owner(course, teacher)
    result = restore_course(db, course)
    log_action(db, teacher.id, "restore", "course", course_id, request=request)
    return result


@router.delete("/{course_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_remove_course(
    course_id: str,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    course = get_course(db, course_id, include_deleted=True)
    if not course:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Course not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    assert_course_owner(course, teacher)
    if course.deleted_at is None:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Course must be soft-deleted before permanent deletion",
            context={"resource_type": "course", "course_id": course_id},
        )
    # Hydrate before logging, same reason as ``remove_course``.
    populate_spine_texts(db, [course])
    log_action(
        db,
        teacher.id,
        "permanent_delete",
        "course",
        course_id,
        details={"title": course.title},
        request=request,
    )
    permanently_delete_course(db, course)
