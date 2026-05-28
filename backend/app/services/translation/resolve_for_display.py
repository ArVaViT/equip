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
from dataclasses import dataclass
from typing import cast

from sqlalchemy.orm import Session  # noqa: TC002

from app.models.announcement import Announcement  # noqa: TC001
from app.models.assignment import Assignment  # noqa: TC001
from app.models.chapter_block import ChapterBlock  # noqa: TC001
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
from app.services.content_versions import (
    fetch_cv_course_text_bulk,
    fetch_cv_text_bulk,
    maybe_compare_and_log,
)
from app.services.language_detection import detect_locale


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
    """Return a map ``(entity_id, field) -> text`` for ok course-level rows.

    Sourced exclusively from ``content_versions`` (Phase 4 made cv the
    primary read store; Phase 5a removed the legacy fallback branch).
    """
    return fetch_cv_course_text_bulk(db, course_ids=course_ids, display_locale=display_locale)


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


def _build_localized_course[T: CourseSummary | CourseResponse](
    schema_cls: type[T],
    course: Course,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
    *,
    db: Session | None = None,
) -> T:
    """Shared body for ``build_localized_course_summary`` /
    ``_response``. The two were byte-for-byte identical except for the
    return-type / ``model_validate`` target — this collapses them.

    Phase 2 dual-read: when ``db`` is set, fires the sample-gated
    comparator for both ``title`` and ``description``. Pass ``db``
    from API call sites (course catalog, user enrollment list); the
    test surface that builds an in-memory overlay leaves ``db=None``
    and the comparator stays inert.

    ``cast(T, …)`` is required because Pydantic's ``model_copy``
    signature is ``Self`` and mypy can't narrow ``Self`` back to ``T``
    through the bound union. The cast is sound: ``base`` was just
    validated as ``T``, so ``base.model_copy(...)`` is also ``T``.
    """
    title = pick_localized_text(course, "title", course.title, overlay, display_locale)
    desc = _localize_optional_description(course, course.description, overlay, display_locale)
    if db is not None:
        source_locale = normalize_locale(course.source_locale)
        maybe_compare_and_log(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            source_locale=source_locale,
            display_locale=display_locale,
            base_source_text=course.title,
            legacy_text=title,
        )
        maybe_compare_and_log(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="description",
            source_locale=source_locale,
            display_locale=display_locale,
            base_source_text=course.description,
            legacy_text=desc,
        )
    base = schema_cls.model_validate(course, from_attributes=True)
    if title == base.title and desc == base.description:
        return cast("T", base)
    return cast("T", base.model_copy(update={"title": title, "description": desc}))


def build_localized_course_summary(
    course: Course,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
    *,
    db: Session | None = None,
) -> CourseSummary:
    return _build_localized_course(CourseSummary, course, overlay, display_locale, db=db)


def build_localized_course_response(
    course: Course,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
    *,
    db: Session | None = None,
) -> CourseResponse:
    return _build_localized_course(CourseResponse, course, overlay, display_locale, db=db)


def fetch_overlay_triples_bulk(
    db: Session,
    keys: list[tuple[str, str, str]],
    display_locale: LocaleCode,
) -> dict[tuple[str, str, str], str]:
    """Bulk-fetch overlay rows keyed by ``(entity_type, entity_id, field)``.

    Sourced exclusively from ``content_versions`` (Phase 4 made cv the
    primary read store; Phase 5a removed the legacy fallback branch).
    """
    return fetch_cv_text_bulk(db, keys, display_locale)


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
    # Per-entity source-language detection: when the base text's
    # actual language matches the display locale, return base and
    # skip whatever overlay might exist for this key. The overlay
    # might be a stale wrong-direction row left over from before
    # per-entity detection in the pipeline (#528) — serving it
    # would give the student text in the wrong language.
    #
    # When detection has no signal (short text, pure punctuation,
    # None), it returns None and we fall through to the legacy rule
    # that uses ``source_locale`` (the course's declared value) for
    # the equality check.
    detected_source = detect_locale(base) if base is not None else None
    effective_source = detected_source or source_locale
    if base is not None and effective_source == display_locale:
        return base
    key = (entity_type, entity_id, field)
    if key in overlay:
        return overlay[key]
    if base is None:
        return None
    return overlay.get(key, base)


@dataclass(frozen=True, slots=True)
class Localizer:
    """Per-request translation-overlay lookup.

    Captures the overlay map plus the ``source_locale`` / ``display_locale``
    pair so every call site drops from the 7-arg ``pick_overlay_value`` to
    a 4-arg ``loc.pick(entity_type, id, field, base)``. The per-request
    constants live on the instance; the call site only carries what
    actually varies between rows.

    Construct one per response; pass it down to inner row-builders.

    Phase 2 dual-read: when constructed with ``Localizer.build`` the
    instance holds a reference to the session, and every ``pick`` call
    fires the sample-gated dual-read comparator behind the legacy
    return value. Legacy direct construction (``Localizer(overlay,
    source, display)``) leaves ``db=None`` and the comparator never
    fires — keeps the existing tests unchanged.
    """

    overlay: dict[tuple[str, str, str], str]
    source_locale: LocaleCode
    display_locale: LocaleCode
    db: Session | None = None

    def pick(self, entity_type: str, entity_id: str, field: str, base: str | None) -> str | None:
        result = pick_overlay_value(
            self.overlay,
            entity_type,
            entity_id,
            field,
            base,
            source_locale=self.source_locale,
            display_locale=self.display_locale,
        )
        if self.db is not None:
            # Side-effect-only: log a structured warning when the new
            # store would have returned something different. Sampled at
            # the env-controlled rate (default 0.0 / disabled). Wrapped
            # internally with broad except so a comparator failure
            # never affects the user's response.
            maybe_compare_and_log(
                self.db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                source_locale=self.source_locale,
                display_locale=self.display_locale,
                base_source_text=base,
                legacy_text=result,
            )
        return result

    @classmethod
    def build(
        cls,
        db: Session,
        specs: list[tuple[str, str, str]],
        *,
        source_locale: LocaleCode,
        display_locale: LocaleCode,
    ) -> Localizer:
        """Bulk-fetch the overlay rows for ``specs`` and wrap them in a
        ``Localizer``. Convenience constructor for the common pattern of
        ``Localizer(fetch_overlay_triples_bulk(...), source, display)``.

        Hooks the session into the returned instance so ``pick`` can
        fire the Phase 2 dual-read comparator on each call.
        """
        return cls(
            overlay=fetch_overlay_triples_bulk(db, specs, display_locale),
            source_locale=source_locale,
            display_locale=display_locale,
            db=db,
        )


@dataclass(frozen=True)
class ChapterLocaleContext:
    """Single-fetch resolution of every locale/access fact a chapter route needs.

    Previously the three helpers below each ran their own chapter→module→course
    join — every block / assignment / quiz GET paid 2-3 round-trips just to
    decide which overlay path to take. ``resolve_chapter_locale_context`` joins
    once and exposes every derived value, then the legacy helpers delegate
    here so existing callers keep working.

    Fields:
        found:              True when the chapter (and its module + course) all
                            exist and are not soft-deleted.
        source_locale:      The chapter's course's source locale. Defaults to
                            ``"ru"`` when ``found`` is False.
        is_owner_or_admin:  True when ``current_user`` owns the course or is an
                            admin — used by the editor ``?source=1`` gate.
        apply_overlay:      True when the API should show localised metadata
                            to this caller (matches
                            ``should_apply_course_translation_overlay``).
    """

    found: bool
    source_locale: LocaleCode
    is_owner_or_admin: bool
    apply_overlay: bool


def resolve_chapter_locale_context(
    db: Session,
    *,
    chapter_id: str,
    current_user: User | None,
) -> ChapterLocaleContext:
    """Run the chapter→course join once and derive every locale/access fact."""
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
        # Match the legacy fall-throughs: missing chapter ⇒ ru source, no
        # ownership, apply overlay (the safe default for unknown viewers).
        return ChapterLocaleContext(
            found=False,
            source_locale="ru",
            is_owner_or_admin=False,
            apply_overlay=True,
        )
    is_admin = current_user is not None and current_user.role == UserRole.ADMIN.value
    is_owner = (
        current_user is not None
        and course.created_by is not None
        and _str_uuid(course.created_by) == _str_uuid(current_user.id)
    )
    return ChapterLocaleContext(
        found=True,
        source_locale=normalize_locale(course.source_locale),
        is_owner_or_admin=is_owner or is_admin,
        apply_overlay=should_apply_course_translation_overlay(course=course, current_user=current_user),
    )


def get_course_source_locale_for_chapter(db: Session, chapter_id: str) -> LocaleCode:
    """Return ``courses.source_locale`` for the chapter's course (fallback ``ru``).

    Legacy single-fact helper. Prefer ``resolve_chapter_locale_context`` when
    a route already needs more than one fact about the chapter's course —
    that single helper folds these three queries into one.
    """
    return resolve_chapter_locale_context(db, chapter_id=chapter_id, current_user=None).source_locale


def should_apply_course_translation_overlay_for_chapter(
    db: Session,
    *,
    chapter_id: str,
    current_user: User | None,
) -> bool:
    """Mirror ``should_apply_course_translation_overlay`` using the chapter's course.

    Legacy single-fact helper. Prefer ``resolve_chapter_locale_context``
    when the same route also needs ``source_locale`` or ``is_owner_or_admin``.
    """
    return resolve_chapter_locale_context(db, chapter_id=chapter_id, current_user=current_user).apply_overlay


def is_chapter_course_owner_or_admin(
    db: Session,
    *,
    chapter_id: str,
    current_user: User | None,
) -> bool:
    """Return True when ``current_user`` owns the chapter's course or is admin.

    Used by the editor-only ``?source=1`` gate on the chapter-scoped read
    endpoints (``/quizzes/chapter/{id}``, ``/assignments/chapter/{id}``,
    ``/blocks/chapter/{id}``). Returning source content to a regular student
    would leak unredacted teacher drafts, so the param is gated.

    Legacy single-fact helper. Prefer ``resolve_chapter_locale_context``
    when the same route also needs ``source_locale`` or ``apply_overlay``.
    """
    return resolve_chapter_locale_context(db, chapter_id=chapter_id, current_user=current_user).is_owner_or_admin


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

    loc = Localizer.build(
        db,
        specs,
        source_locale=normalize_locale(course.source_locale),
        display_locale=display_locale,
    )

    ct = loc.pick("course", course.id, "title", course.title) or course.title
    cd = loc.pick("course", course.id, "description", course.description)

    new_modules: list[ModuleResponse] = []
    for mod in course.modules:
        mt = loc.pick("module", str(mod.id), "title", mod.title) or mod.title
        md = loc.pick("module", str(mod.id), "description", mod.description)
        new_chapters: list[ChapterResponse] = []
        for ch in mod.chapters:
            cht = loc.pick("chapter", str(ch.id), "title", ch.title) or ch.title
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
    loc = Localizer.build(db, specs, source_locale=source_locale, display_locale=display_locale)

    new_title = loc.pick("quiz", str(quiz.id), "title", quiz.title) or quiz.title
    new_desc = loc.pick("quiz", str(quiz.id), "description", quiz.description)
    new_questions: list[QuizQuestionStudentResponse] = []
    for qn in quiz.questions:
        qt = loc.pick("quiz_question", str(qn.id), "question_text", qn.question_text) or qn.question_text
        new_opts: list[QuizOptionStudentResponse] = []
        for opt in qn.options:
            ot = loc.pick("quiz_option", str(opt.id), "option_text", opt.option_text) or opt.option_text
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
    loc = Localizer.build(db, specs, source_locale=source_locale, display_locale=display_locale)
    out: list[AssignmentResponse] = []
    for a in assignments:
        base = AssignmentResponse.model_validate(a, from_attributes=True)
        t = loc.pick("assignment", str(a.id), "title", a.title) or a.title
        d = loc.pick("assignment", str(a.id), "description", a.description)
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
    specs: list[tuple[str, str, str]] = [
        ("chapter_block", str(b.id), "content") for b in blocks if b.content and str(b.content).strip()
    ]
    loc = Localizer.build(db, specs, source_locale=source_locale, display_locale=display_locale)
    out: list[BlockResponse] = []
    for b in blocks:
        base = BlockResponse.model_validate(b, from_attributes=True)
        content = b.content
        if not content or not str(content).strip():
            out.append(base)
            continue
        ct = loc.pick("chapter_block", str(b.id), "content", content) or content
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
        *(("chapter", str(ch.id), "title") for ch in module.chapters),
    ]
    loc = Localizer.build(db, specs, source_locale=source_locale, display_locale=display_locale)

    mt = loc.pick("module", str(module.id), "title", module.title) or module.title
    md = loc.pick("module", str(module.id), "description", module.description)
    new_chapters: list[ChapterResponse] = []
    for ch in module.chapters:
        cht = loc.pick("chapter", str(ch.id), "title", ch.title) or ch.title
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
    loc = Localizer.build(db, specs, source_locale=source_locale, display_locale=display_locale)
    out: list[AnnouncementResponse] = []
    for a in announcements:
        base = AnnouncementResponse.model_validate(a, from_attributes=True)
        title = loc.pick("announcement", str(a.id), "title", a.title) or a.title
        content = loc.pick("announcement", str(a.id), "content", a.content) or a.content
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
    loc = Localizer.build(db, specs, source_locale=source_locale, display_locale=display_locale)
    out: list[CourseEventResponse] = []
    for e in events:
        base = CourseEventResponse.model_validate(e, from_attributes=True)
        title = loc.pick("course_event", str(e.id), "title", e.title) or e.title
        description = loc.pick("course_event", str(e.id), "description", e.description)
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
    "is_chapter_course_owner_or_admin",
    "localize_announcement_rows",
    "localize_assignment_rows",
    "localize_chapter_block_rows",
    "localize_course_event_rows",
    "pick_overlay_value",
    "should_apply_course_translation_overlay",
    "should_apply_course_translation_overlay_for_chapter",
]
