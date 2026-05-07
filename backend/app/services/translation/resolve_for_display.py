"""Map stored ``content_translations`` onto course read models for the API.

The requested UI locale (``Accept-Language``) maps to a ``content_translations``
row per ``(entity_id, field, locale)`` when the translation pipeline (or
manual human edits) materialised one with ``status='ok'``. We **always prefer**
that text for the **same** display locale, even if ``courses.source_locale`` is
set to the same code but the source columns still contain a different
language (legacy authoring drift). The canonical text still lives on
``courses.*`` for owners/admins and as a fallback when no row exists.

Authoring views (owner + admin) always see the source columns so editors are
not surprised by machine translations when the UI is in another language.
"""

from __future__ import annotations

import uuid

from sqlalchemy import tuple_
from sqlalchemy.orm import Session  # noqa: TC002

from app.models.announcement import Announcement  # noqa: TC001
from app.models.assignment import Assignment  # noqa: TC001
from app.models.chapter_block import ChapterBlock  # noqa: TC001
from app.models.content_translation import ContentTranslation
from app.models.course import Chapter, Course, Module
from app.models.course_event import CourseEvent  # noqa: TC001
from app.models.quiz import Quiz  # noqa: TC001
from app.models.user import User, UserRole
from app.schemas.announcement import AnnouncementResponse
from app.schemas.assignment import AssignmentResponse
from app.schemas.calendar import CourseEventResponse
from app.schemas.chapter_block import BlockResponse
from app.schemas.course import ChapterResponse, CourseResponse, CourseSummary, ModuleResponse
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.quiz import QuizOptionStudentResponse, QuizQuestionStudentResponse, QuizStudentResponse


def _str_uuid(v: str | uuid.UUID) -> str:
    """Case-normalise UUIDs so SQLite/Postgres string forms compare equal."""
    return str(uuid.UUID(str(v)))


def should_apply_course_translation_overlay(*, course: Course, current_user: User | None) -> bool:
    """Return True when the API should show localized metadata to this caller."""
    if current_user is None:
        return True
    if current_user.role == UserRole.ADMIN.value:
        return False
    is_owner = course.created_by is not None and _str_uuid(course.created_by) == _str_uuid(current_user.id)
    return not is_owner


def batch_fetch_course_translations(
    db: Session,
    *,
    course_ids: list[str],
    display_locale: LocaleCode,
) -> dict[tuple[str, str], str]:
    """Return a map ``(entity_id, field) -> text`` for ok course-level rows."""
    if not course_ids:
        return {}
    rows = (
        db.query(ContentTranslation)
        .filter(
            ContentTranslation.entity_type == "course",
            ContentTranslation.entity_id.in_(course_ids),
            ContentTranslation.locale == display_locale,
            ContentTranslation.field.in_(("title", "description")),
            ContentTranslation.status == "ok",
        )
        .all()
    )
    return {(r.entity_id, r.field): r.text for r in rows}


def pick_localized_text(
    course: Course,
    field: str,
    base: str,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
) -> str:
    key = (course.id, field)
    if key in overlay:
        return overlay[key]
    if normalize_locale(course.source_locale) == display_locale:
        return base
    return overlay.get(key, base)


def _localize_optional_description(
    course: Course,
    base: str | None,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
) -> str | None:
    dkey = (course.id, "description")
    if dkey in overlay:
        return overlay[dkey]
    if base is not None:
        return pick_localized_text(course, "description", base, overlay, display_locale)
    if normalize_locale(course.source_locale) == display_locale:
        return None
    return overlay.get(dkey)


def build_localized_course_summary(
    course: Course,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
) -> CourseSummary:
    title = pick_localized_text(course, "title", course.title, overlay, display_locale)
    desc = _localize_optional_description(course, course.description, overlay, display_locale)
    base = CourseSummary.model_validate(course, from_attributes=True)
    if title == base.title and desc == base.description:
        return base
    return base.model_copy(update={"title": title, "description": desc})


def build_localized_course_response(
    course: Course,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
) -> CourseResponse:
    title = pick_localized_text(course, "title", course.title, overlay, display_locale)
    desc = _localize_optional_description(course, course.description, overlay, display_locale)
    base = CourseResponse.model_validate(course, from_attributes=True)
    if title == base.title and desc == base.description:
        return base
    return base.model_copy(update={"title": title, "description": desc})


def fetch_overlay_triples_bulk(
    db: Session,
    keys: list[tuple[str, str, str]],
    display_locale: LocaleCode,
) -> dict[tuple[str, str, str], str]:
    """Bulk-fetch ``content_translations`` rows keyed by ``(entity_type, entity_id, field)``."""
    if not keys:
        return {}
    uniq = list(dict.fromkeys(keys))
    rows = (
        db.query(ContentTranslation)
        .filter(
            tuple_(
                ContentTranslation.entity_type,
                ContentTranslation.entity_id,
                ContentTranslation.field,
            ).in_(uniq),
            ContentTranslation.locale == display_locale,
            ContentTranslation.status == "ok",
        )
        .all()
    )
    return {(r.entity_type, r.entity_id, r.field): r.text for r in rows}


def pick_overlay_value(
    overlay: dict[tuple[str, str, str], str],
    entity_type: str,
    entity_id: str,
    field: str,
    base: str | None,
    *,
    source_locale: LocaleCode,
    display_locale: LocaleCode,
) -> str | None:
    key = (entity_type, entity_id, field)
    if key in overlay:
        return overlay[key]
    if base is None:
        return None
    if source_locale == display_locale:
        return base
    return overlay.get(key, base)


def get_course_source_locale_for_chapter(db: Session, chapter_id: str) -> LocaleCode:
    """Return ``courses.source_locale`` for the chapter's course (fallback ``ru``)."""
    row = (
        db.query(Course.source_locale)
        .join(Module, Module.course_id == Course.id)
        .join(Chapter, Chapter.module_id == Module.id)
        .filter(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Course.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        return "ru"
    return normalize_locale(row[0])


def should_apply_course_translation_overlay_for_chapter(
    db: Session,
    *,
    chapter_id: str,
    current_user: User | None,
) -> bool:
    """Mirror ``should_apply_course_translation_overlay`` using the chapter's course."""
    course = (
        db.query(Course)
        .join(Module, Module.course_id == Course.id)
        .join(Chapter, Chapter.module_id == Module.id)
        .filter(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Course.deleted_at.is_(None),
        )
        .first()
    )
    if course is None:
        return True
    return should_apply_course_translation_overlay(course=course, current_user=current_user)


def build_localized_course_response_with_tree(
    db: Session,
    course: Course,
    display_locale: LocaleCode,
) -> CourseResponse:
    """Localized course title/description plus module and chapter titles for students."""
    specs: list[tuple[str, str, str]] = [
        ("course", course.id, "title"),
        ("course", course.id, "description"),
    ]
    for mod in course.modules:
        specs.extend(
            [
                ("module", str(mod.id), "title"),
                ("module", str(mod.id), "description"),
            ]
        )
        for ch in mod.chapters:
            specs.append(("chapter", str(ch.id), "title"))

    overlay_t = fetch_overlay_triples_bulk(db, specs, display_locale)
    source_locale = normalize_locale(course.source_locale)

    ct = (
        pick_overlay_value(
            overlay_t,
            "course",
            course.id,
            "title",
            course.title,
            source_locale=source_locale,
            display_locale=display_locale,
        )
        or course.title
    )
    cd = pick_overlay_value(
        overlay_t,
        "course",
        course.id,
        "description",
        course.description,
        source_locale=source_locale,
        display_locale=display_locale,
    )

    new_modules: list[ModuleResponse] = []
    for mod in course.modules:
        mt = (
            pick_overlay_value(
                overlay_t,
                "module",
                str(mod.id),
                "title",
                mod.title,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or mod.title
        )
        md = pick_overlay_value(
            overlay_t,
            "module",
            str(mod.id),
            "description",
            mod.description,
            source_locale=source_locale,
            display_locale=display_locale,
        )
        new_chapters: list[ChapterResponse] = []
        for ch in mod.chapters:
            cht = (
                pick_overlay_value(
                    overlay_t,
                    "chapter",
                    str(ch.id),
                    "title",
                    ch.title,
                    source_locale=source_locale,
                    display_locale=display_locale,
                )
                or ch.title
            )
            ch_base = ChapterResponse.model_validate(ch, from_attributes=True)
            new_chapters.append(ch_base.model_copy(update={"title": cht}))
        mod_base = ModuleResponse.model_validate(mod, from_attributes=True)
        new_modules.append(mod_base.model_copy(update={"title": mt, "description": md, "chapters": new_chapters}))

    base = CourseResponse.model_validate(course, from_attributes=True)
    return base.model_copy(update={"title": ct, "description": cd, "modules": new_modules})


def build_localized_quiz_student_response(
    db: Session,
    quiz: Quiz,
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> QuizStudentResponse:
    """Apply ``content_translations`` to a quiz payload shown to students."""
    specs: list[tuple[str, str, str]] = [
        ("quiz", str(quiz.id), "title"),
        ("quiz", str(quiz.id), "description"),
    ]
    for qn in quiz.questions:
        specs.append(("quiz_question", str(qn.id), "question_text"))
        for opt in qn.options:
            specs.append(("quiz_option", str(opt.id), "option_text"))
    overlay_t = fetch_overlay_triples_bulk(db, specs, display_locale)
    new_title = (
        pick_overlay_value(
            overlay_t,
            "quiz",
            str(quiz.id),
            "title",
            quiz.title,
            source_locale=source_locale,
            display_locale=display_locale,
        )
        or quiz.title
    )
    new_desc = pick_overlay_value(
        overlay_t,
        "quiz",
        str(quiz.id),
        "description",
        quiz.description,
        source_locale=source_locale,
        display_locale=display_locale,
    )
    new_questions: list[QuizQuestionStudentResponse] = []
    for qn in quiz.questions:
        qt = (
            pick_overlay_value(
                overlay_t,
                "quiz_question",
                str(qn.id),
                "question_text",
                qn.question_text,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or qn.question_text
        )
        new_opts: list[QuizOptionStudentResponse] = []
        for opt in qn.options:
            ot = (
                pick_overlay_value(
                    overlay_t,
                    "quiz_option",
                    str(opt.id),
                    "option_text",
                    opt.option_text,
                    source_locale=source_locale,
                    display_locale=display_locale,
                )
                or opt.option_text
            )
            ob = QuizOptionStudentResponse.model_validate(opt, from_attributes=True)
            new_opts.append(ob.model_copy(update={"option_text": ot}))
        qb = QuizQuestionStudentResponse.model_validate(qn, from_attributes=True)
        new_questions.append(qb.model_copy(update={"question_text": qt, "options": new_opts}))
    base = QuizStudentResponse.model_validate(quiz, from_attributes=True)
    return base.model_copy(update={"title": new_title, "description": new_desc, "questions": new_questions})


def localize_assignment_rows(
    db: Session,
    assignments: list[Assignment],
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> list[AssignmentResponse]:
    if not assignments:
        return []
    specs: list[tuple[str, str, str]] = []
    for a in assignments:
        specs.extend(
            [
                ("assignment", str(a.id), "title"),
                ("assignment", str(a.id), "description"),
            ]
        )
    overlay_t = fetch_overlay_triples_bulk(db, specs, display_locale)
    out: list[AssignmentResponse] = []
    for a in assignments:
        base = AssignmentResponse.model_validate(a, from_attributes=True)
        t = (
            pick_overlay_value(
                overlay_t,
                "assignment",
                str(a.id),
                "title",
                a.title,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or a.title
        )
        d = pick_overlay_value(
            overlay_t,
            "assignment",
            str(a.id),
            "description",
            a.description,
            source_locale=source_locale,
            display_locale=display_locale,
        )
        out.append(base.model_copy(update={"title": t, "description": d}))
    return out


def localize_chapter_block_rows(
    db: Session,
    blocks: list[ChapterBlock],
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> list[BlockResponse]:
    """Apply stored translations to TipTap HTML stored on chapter blocks."""
    if not blocks:
        return []
    specs: list[tuple[str, str, str]] = []
    for b in blocks:
        if b.content and str(b.content).strip():
            specs.append(("chapter_block", str(b.id), "content"))
    overlay_t = fetch_overlay_triples_bulk(db, specs, display_locale)
    out: list[BlockResponse] = []
    for b in blocks:
        base = BlockResponse.model_validate(b, from_attributes=True)
        content = b.content
        if not content or not str(content).strip():
            out.append(base)
            continue
        ct = (
            pick_overlay_value(
                overlay_t,
                "chapter_block",
                str(b.id),
                "content",
                content,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or content
        )
        out.append(base.model_copy(update={"content": ct}))
    return out


def build_localized_module_response(
    db: Session,
    module: Module,
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> ModuleResponse:
    """Localized module title/description plus chapter titles.

    Mirror of ``build_localized_course_response_with_tree`` but scoped to a
    single module — the dedicated module-detail endpoint hits this so a
    student opening a module sees module + chapter titles in the active
    locale (was returning raw RU even though chapter titles were already in
    ``content_translations``).
    """
    specs: list[tuple[str, str, str]] = [
        ("module", str(module.id), "title"),
        ("module", str(module.id), "description"),
    ]
    for ch in module.chapters:
        specs.append(("chapter", str(ch.id), "title"))
    overlay_t = fetch_overlay_triples_bulk(db, specs, display_locale)

    mt = (
        pick_overlay_value(
            overlay_t,
            "module",
            str(module.id),
            "title",
            module.title,
            source_locale=source_locale,
            display_locale=display_locale,
        )
        or module.title
    )
    md = pick_overlay_value(
        overlay_t,
        "module",
        str(module.id),
        "description",
        module.description,
        source_locale=source_locale,
        display_locale=display_locale,
    )
    new_chapters: list[ChapterResponse] = []
    for ch in module.chapters:
        cht = (
            pick_overlay_value(
                overlay_t,
                "chapter",
                str(ch.id),
                "title",
                ch.title,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or ch.title
        )
        ch_base = ChapterResponse.model_validate(ch, from_attributes=True)
        new_chapters.append(ch_base.model_copy(update={"title": cht}))
    base = ModuleResponse.model_validate(module, from_attributes=True)
    return base.model_copy(update={"title": mt, "description": md, "chapters": new_chapters})


def localize_announcement_rows(
    db: Session,
    announcements: list[Announcement],
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> list[AnnouncementResponse]:
    """Apply stored translations to teacher-authored announcement rows."""
    if not announcements:
        return []
    specs: list[tuple[str, str, str]] = []
    for a in announcements:
        specs.append(("announcement", str(a.id), "title"))
        if a.content and str(a.content).strip():
            specs.append(("announcement", str(a.id), "content"))
    overlay_t = fetch_overlay_triples_bulk(db, specs, display_locale)
    out: list[AnnouncementResponse] = []
    for a in announcements:
        base = AnnouncementResponse.model_validate(a, from_attributes=True)
        title = (
            pick_overlay_value(
                overlay_t,
                "announcement",
                str(a.id),
                "title",
                a.title,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or a.title
        )
        content = (
            pick_overlay_value(
                overlay_t,
                "announcement",
                str(a.id),
                "content",
                a.content,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or a.content
        )
        out.append(base.model_copy(update={"title": title, "content": content}))
    return out


def localize_course_event_rows(
    db: Session,
    events: list[CourseEvent],
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> list[CourseEventResponse]:
    """Apply stored translations to calendar event rows."""
    if not events:
        return []
    specs: list[tuple[str, str, str]] = []
    for e in events:
        specs.append(("course_event", str(e.id), "title"))
        if e.description and str(e.description).strip():
            specs.append(("course_event", str(e.id), "description"))
    overlay_t = fetch_overlay_triples_bulk(db, specs, display_locale)
    out: list[CourseEventResponse] = []
    for e in events:
        base = CourseEventResponse.model_validate(e, from_attributes=True)
        title = (
            pick_overlay_value(
                overlay_t,
                "course_event",
                str(e.id),
                "title",
                e.title,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or e.title
        )
        description = pick_overlay_value(
            overlay_t,
            "course_event",
            str(e.id),
            "description",
            e.description,
            source_locale=source_locale,
            display_locale=display_locale,
        )
        out.append(base.model_copy(update={"title": title, "description": description}))
    return out


__all__ = [
    "batch_fetch_course_translations",
    "build_localized_course_response",
    "build_localized_course_response_with_tree",
    "build_localized_course_summary",
    "build_localized_module_response",
    "build_localized_quiz_student_response",
    "fetch_overlay_triples_bulk",
    "get_course_source_locale_for_chapter",
    "localize_announcement_rows",
    "localize_assignment_rows",
    "localize_chapter_block_rows",
    "localize_course_event_rows",
    "pick_overlay_value",
    "should_apply_course_translation_overlay",
    "should_apply_course_translation_overlay_for_chapter",
]
