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
from app.models.content_version import ContentVersion
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
from app.schemas.quiz import QuizResponse, QuizStudentResponse
from app.services.content_versions import (
    fetch_cv_course_text_bulk,
    fetch_cv_entity_texts_with_fallback,
    fetch_cv_text_bulk,
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
) -> T:
    """Shared body for ``build_localized_course_summary`` /
    ``_response``. The two were byte-for-byte identical except for the
    return-type / ``model_validate`` target — this collapses them.

    Phase 5g: ``course.title`` / ``course.description`` columns dropped.
    Read path callers MUST call ``populate_spine_texts`` (or its bulk
    cousin) on the course before invoking this — it sets ``.title`` and
    ``.description`` as runtime attributes from cv, so the rest of the
    serialization pipeline keeps working unchanged.
    """
    title = pick_localized_text(course, "title", course.title, overlay, display_locale)
    desc = _localize_optional_description(course, course.description, overlay, display_locale)
    base = schema_cls.model_validate(course, from_attributes=True)
    if title == base.title and desc == base.description:
        return cast("T", base)
    return cast("T", base.model_copy(update={"title": title, "description": desc}))


def build_localized_course_summary(
    course: Course,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
) -> CourseSummary:
    return _build_localized_course(CourseSummary, course, overlay, display_locale)


def build_localized_course_response(
    course: Course,
    overlay: dict[tuple[str, str], str],
    display_locale: LocaleCode,
) -> CourseResponse:
    return _build_localized_course(CourseResponse, course, overlay, display_locale)


def populate_spine_texts(
    db: Session,
    courses: list[Course],
) -> None:
    """Phase 5g: ``courses.title|description`` and ``modules.title|description``
    columns dropped. Hydrate each course (and every loaded module/chapter
    title via the module list) with runtime attributes pulled from cv,
    so downstream serialization that reads ``course.title`` / ``module.title``
    keeps working unchanged.

    Each entity's source_locale fallback is applied per-entity (a course
    declared ``source_locale='ru'`` falls back to its RU row when the
    display lookup is absent). Any-locale tier rescues content authored
    in a locale that's neither the display nor course-declared source.

    Idempotent: hydrating an already-hydrated entity overwrites with
    the same value.
    """
    if not courses:
        return
    # ── courses ───────────────────────────────────────────────────────
    by_src: dict[str, list[str]] = {}
    for c in courses:
        by_src.setdefault(normalize_locale(c.source_locale), []).append(c.id)
    course_texts: dict[tuple[str, str], str | None] = {}
    for src_locale, ids in by_src.items():
        course_texts.update(
            fetch_cv_entity_texts_with_fallback(
                db,
                entity_type="course",
                entity_ids=ids,
                fields=["title", "description"],
                display_locale=src_locale,
                source_locale=src_locale,
            )
        )
    for c in courses:
        c.title = course_texts.get((c.id, "title")) or ""
        c.description = course_texts.get((c.id, "description"))

    # ── modules (all modules across all courses, grouped by parent course's source_locale) ──
    modules_by_src: dict[str, list[Module]] = {}
    for c in courses:
        loaded = getattr(c, "__dict__", {}).get("modules")
        if not loaded:
            continue
        src = normalize_locale(c.source_locale)
        modules_by_src.setdefault(src, []).extend(loaded)
    for src_locale, mods in modules_by_src.items():
        if not mods:
            continue
        bulk = fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="module",
            entity_ids=[str(m.id) for m in mods],
            fields=["title", "description"],
            display_locale=src_locale,
            source_locale=src_locale,
        )
        for m in mods:
            m.title = bulk.get((str(m.id), "title")) or ""
            m.description = bulk.get((str(m.id), "description"))


def populate_module_texts(db: Session, modules: list[Module], *, source_locale: LocaleCode) -> None:
    """Like ``populate_spine_texts`` but for a flat list of modules where
    the caller already knows the shared source_locale (e.g. when iterating
    modules of one course).
    """
    if not modules:
        return
    bulk = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="module",
        entity_ids=[str(m.id) for m in modules],
        fields=["title", "description"],
        display_locale=source_locale,
        source_locale=source_locale,
    )
    for m in modules:
        m.title = bulk.get((str(m.id), "title")) or ""
        m.description = bulk.get((str(m.id), "description"))


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
    """

    overlay: dict[tuple[str, str, str], str]
    source_locale: LocaleCode
    display_locale: LocaleCode

    def pick(self, entity_type: str, entity_id: str, field: str, base: str | None) -> str | None:
        return pick_overlay_value(
            self.overlay,
            entity_type,
            entity_id,
            field,
            base,
            source_locale=self.source_locale,
            display_locale=self.display_locale,
        )

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
        """
        return cls(
            overlay=fetch_overlay_triples_bulk(db, specs, display_locale),
            source_locale=source_locale,
            display_locale=display_locale,
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


def _fetch_quiz_tree_texts(
    db: Session,
    quiz: Quiz,
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> tuple[dict[tuple[str, str], str | None], dict[tuple[str, str], str | None], dict[tuple[str, str], str | None]]:
    """Bulk-fetch every cv text for ``quiz`` + its questions + their options
    at display→source→any locale fallback. Returns three (entity_id, field)
    → text dicts so callers can build whichever response shape they need.

    Phase 5f: ``quizzes.title``, ``quizzes.description``,
    ``quiz_questions.question_text`` and ``quiz_options.option_text``
    were dropped, so cv is the only store. Three calls (one per
    entity_type) keeps the SQL tuple-IN clauses simple and lets each
    use its own ``fields=[]`` list.
    """
    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    quiz_texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="quiz",
        entity_ids=[str(quiz.id)],
        fields=["title", "description"],
        display_locale=display_locale,
        source_locale=source_locale,
    )
    question_ids = [str(qn.id) for qn in quiz.questions]
    question_texts = (
        fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="quiz_question",
            entity_ids=question_ids,
            fields=["question_text"],
            display_locale=display_locale,
            source_locale=source_locale,
        )
        if question_ids
        else {}
    )
    option_ids = [str(opt.id) for qn in quiz.questions for opt in qn.options]
    option_texts = (
        fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="quiz_option",
            entity_ids=option_ids,
            fields=["option_text"],
            display_locale=display_locale,
            source_locale=source_locale,
        )
        if option_ids
        else {}
    )
    return quiz_texts, question_texts, option_texts


def build_localized_quiz_student_response(
    db: Session,
    quiz: Quiz,
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> QuizStudentResponse:
    """Phase 5f: quiz tree text columns dropped — fetch every title /
    description / question_text / option_text from cv with three-tier
    fallback, then assemble the student-facing response.
    """
    quiz_texts, question_texts, option_texts = _fetch_quiz_tree_texts(
        db, quiz, display_locale=display_locale, source_locale=source_locale
    )
    new_questions: list[dict] = []
    for qn in quiz.questions:
        qid = str(qn.id)
        new_opts: list[dict] = []
        for opt in qn.options:
            oid = str(opt.id)
            new_opts.append(
                {
                    "id": opt.id,
                    "option_text": option_texts.get((oid, "option_text")) or "",
                    "order_index": opt.order_index,
                }
            )
        new_questions.append(
            {
                "id": qn.id,
                "question_text": question_texts.get((qid, "question_text")) or "",
                "question_type": qn.question_type,
                "order_index": qn.order_index,
                "points": qn.points,
                "min_words": qn.min_words,
                "options": new_opts,
            }
        )
    return QuizStudentResponse.model_validate(
        {
            "id": quiz.id,
            "chapter_id": quiz.chapter_id,
            "title": quiz_texts.get((str(quiz.id), "title")) or "",
            "description": quiz_texts.get((str(quiz.id), "description")),
            "quiz_type": quiz.quiz_type,
            "max_attempts": quiz.max_attempts,
            "passing_score": quiz.passing_score,
            "questions": new_questions,
        }
    )


def build_quiz_response_from_cv(
    db: Session,
    quiz: Quiz,
    *,
    source_locale: LocaleCode,
) -> QuizResponse:
    """Teacher-facing quiz response with all texts pulled from cv at the
    course's source_locale (with any-locale fallback). Used by the
    create / update / source=1 list routes.
    """
    quiz_texts, question_texts, option_texts = _fetch_quiz_tree_texts(
        db, quiz, display_locale=source_locale, source_locale=source_locale
    )
    new_questions: list[dict] = []
    for qn in quiz.questions:
        qid = str(qn.id)
        new_opts: list[dict] = []
        for opt in qn.options:
            oid = str(opt.id)
            new_opts.append(
                {
                    "id": opt.id,
                    "option_text": option_texts.get((oid, "option_text")) or "",
                    "is_correct": opt.is_correct,
                    "order_index": opt.order_index,
                }
            )
        new_questions.append(
            {
                "id": qn.id,
                "question_text": question_texts.get((qid, "question_text")) or "",
                "question_type": qn.question_type,
                "order_index": qn.order_index,
                "points": qn.points,
                "min_words": qn.min_words,
                "options": new_opts,
            }
        )
    return QuizResponse.model_validate(
        {
            "id": quiz.id,
            "chapter_id": quiz.chapter_id,
            "title": quiz_texts.get((str(quiz.id), "title")) or "",
            "description": quiz_texts.get((str(quiz.id), "description")),
            "quiz_type": quiz.quiz_type,
            "max_attempts": quiz.max_attempts,
            "passing_score": quiz.passing_score,
            "created_at": quiz.created_at,
            "updated_at": quiz.updated_at,
            "questions": new_questions,
        }
    )


def localize_assignment_rows(
    db: Session,
    assignments: list[Assignment],
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> list[AssignmentResponse]:
    """Phase 5e3: ``assignments.title`` + ``description`` columns dropped.
    Both texts live in ``content_versions`` now. Resolve each via a
    three-tier fallback (display → source → any-locale).
    """
    if not assignments:
        return []
    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    ids = [str(a.id) for a in assignments]
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="assignment",
        entity_ids=ids,
        fields=["title", "description"],
        display_locale=display_locale,
        source_locale=source_locale,
    )
    out: list[AssignmentResponse] = []
    for a in assignments:
        aid = str(a.id)
        out.append(
            AssignmentResponse.model_validate(
                {
                    "id": a.id,
                    "chapter_id": a.chapter_id,
                    "title": texts.get((aid, "title")) or "",
                    "description": texts.get((aid, "description")),
                    "max_score": a.max_score,
                    "due_date": a.due_date,
                    "created_at": a.created_at,
                    "updated_at": a.updated_at,
                }
            )
        )
    return out


def localize_chapter_block_rows(
    db: Session,
    blocks: list[ChapterBlock],
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> list[BlockResponse]:
    """Apply stored translations to TipTap HTML stored on chapter blocks.

    Phase 5e2: the legacy ``content`` column was dropped. Both the
    source text and the localised overlay live in ``content_versions``
    now. Build the response manually because ``model_validate(block)``
    would try to read ``block.content`` (no longer an attribute).

    Three-tier fallback: display_locale → source_locale → any-locale.
    The any-locale tier rescues blocks whose content was authored in a
    locale that's neither display nor course-declared source (an edge
    case from the per-field-detection world).
    """
    if not blocks:
        return []
    block_ids = [str(b.id) for b in blocks]
    # All-locale bulk fetch: one indexed query covers display + source
    # + any-locale tiers. Ordered by created_at so we deterministically
    # pick the earliest if multiple rows exist per block at a locale.
    rows = (
        db.query(ContentVersion.entity_id, ContentVersion.locale, ContentVersion.text)
        .filter(
            ContentVersion.entity_type == "chapter_block",
            ContentVersion.entity_id.in_(block_ids),
            ContentVersion.field == "content",
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == "ok",
        )
        .order_by(ContentVersion.entity_id, ContentVersion.created_at)
        .all()
    )
    by_block_locale: dict[tuple[str, str], str] = {}
    any_by_block: dict[str, str] = {}
    for eid, locale, text in rows:
        by_block_locale.setdefault((eid, locale), text)
        any_by_block.setdefault(eid, text)
    out: list[BlockResponse] = []
    for b in blocks:
        bid = str(b.id)
        content = (
            by_block_locale.get((bid, display_locale))
            or by_block_locale.get((bid, source_locale))
            or any_by_block.get(bid)
        )
        out.append(
            BlockResponse.model_validate(
                {
                    "id": b.id,
                    "chapter_id": b.chapter_id,
                    "block_type": b.block_type,
                    "order_index": b.order_index,
                    "content": content,
                    "quiz_id": b.quiz_id,
                    "assignment_id": b.assignment_id,
                    "file_bucket": b.file_bucket,
                    "file_path": b.file_path,
                    "file_name": b.file_name,
                    "created_at": b.created_at,
                    "updated_at": b.updated_at,
                }
            )
        )
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
    """Phase 5e5: ``announcements.title`` + ``content`` columns dropped.
    Both texts live in cv now. Resolve each via the three-tier fallback
    (display → source → any-locale).
    """
    if not announcements:
        return []
    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    ids = [str(a.id) for a in announcements]
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="announcement",
        entity_ids=ids,
        fields=["title", "content"],
        display_locale=display_locale,
        source_locale=source_locale,
    )
    out: list[AnnouncementResponse] = []
    for a in announcements:
        aid = str(a.id)
        out.append(
            AnnouncementResponse.model_validate(
                {
                    "id": a.id,
                    "title": texts.get((aid, "title")) or "",
                    "content": texts.get((aid, "content")) or "",
                    "course_id": a.course_id,
                    "created_by": a.created_by,
                    "created_at": a.created_at,
                    "updated_at": a.updated_at,
                }
            )
        )
    return out


def localize_course_event_rows(
    db: Session,
    events: list[CourseEvent],
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
) -> list[CourseEventResponse]:
    """Phase 5e4: ``course_events.title`` + ``description`` columns dropped.
    Both texts live in cv now. Resolve each via the three-tier
    fallback (display → source → any-locale).
    """
    if not events:
        return []
    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    ids = [str(e.id) for e in events]
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course_event",
        entity_ids=ids,
        fields=["title", "description"],
        display_locale=display_locale,
        source_locale=source_locale,
    )
    out: list[CourseEventResponse] = []
    for e in events:
        eid = str(e.id)
        out.append(
            CourseEventResponse.model_validate(
                {
                    "id": e.id,
                    "course_id": e.course_id,
                    "title": texts.get((eid, "title")) or "",
                    "description": texts.get((eid, "description")),
                    "event_type": e.event_type,
                    "event_date": e.event_date,
                    "created_by": e.created_by,
                    "created_at": e.created_at,
                }
            )
        )
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
