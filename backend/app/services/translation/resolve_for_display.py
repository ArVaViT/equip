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
from typing import Literal

from sqlalchemy.orm import Session  # noqa: TC002

from app.models.announcement import Announcement  # noqa: TC001
from app.models.assignment import Assignment  # noqa: TC001
from app.models.chapter_block import ChapterBlock  # noqa: TC001
from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Chapter, Course, Module
from app.models.course_event import CourseEvent  # noqa: TC001
from app.models.quiz import Quiz  # noqa: TC001
from app.models.user import User, UserRole
from app.schemas.announcement import AnnouncementResponse
from app.schemas.assignment import AssignmentResponse
from app.schemas.calendar import CourseEventResponse
from app.schemas.chapter_block import BlockResponse
from app.schemas.course import (
    ChapterResponse,
    CourseDashboardSummary,
    CourseResponse,
    CourseSummary,
    ModuleResponse,
)
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.quiz import QuizResponse, QuizStudentResponse
from app.services.content_versions import (
    fetch_cv_entity_texts_with_fallback,
    fetch_cv_text_bulk,
)
from app.services.language_detection import carries_language, detect_locale
from app.services.translation.service import is_translation_enabled


def _str_uuid(v: str | uuid.UUID) -> str:
    """Case-normalise UUIDs so SQLite/Postgres string forms compare equal."""
    return str(uuid.UUID(str(v)))


def should_apply_course_translation_overlay(*, course: Course, current_user: User | None) -> bool:
    """Whether a *read* shows this caller the translation. Always, now.

    This used to answer False for admins and for the course's owner, so
    that a teacher viewing their Russian course in an English UI could
    not accidentally save the English translation back over their source
    text. The risk is real, but the guard was in the wrong place: it
    applied to every read, not to editing.

    What it produced is a platform that lies to the people responsible
    for it. The admin who switches the interface to German — to see what
    a German student sees — is served Russian, on every page, and
    concludes the translations are broken. So does the teacher checking
    their own course. The two people most able to catch a translation
    defect were the two who could never see one.

    Editing is protected by the thing that was always the real answer:
    an explicit ``?source=1``, gated to owner and admin, which every
    editor surface in the web app already sends
    (``getCourseForEdit``, ``getModuleForEdit``, blocks, quizzes,
    assignments, announcements, calendar). Reading is reading, and a
    reader gets the language they chose.

    Kept as a function rather than deleted at the call sites: it is the
    one place to state the rule, and a future surface that genuinely
    needs the source has somewhere to argue its case.
    """
    del course, current_user  # the rule no longer depends on either
    return True


def fetch_course_titles_by_id(
    db: Session,
    course_ids: list[str],
    *,
    display_locale: LocaleCode,
    fallback: Literal["auto", "none", "source_then_any"] = "auto",
) -> dict[str, str]:
    """Return ``{course_id -> course title}`` at ``display_locale``.

    One bulk query per source_locale group. Empty when no course_ids
    supplied; a course with no title in this language comes back as ``""``.

    ``fallback`` is passed straight through to the cv reader. Readers take
    the default and get nothing rather than another language. A caller that
    must print *something* — the certificate, which would otherwise leave a
    blank line on a document somebody hands an employer — asks for
    ``"source_then_any"`` and says why at the call site.

    Used by every endpoint that needs to label a course in its title
    column without paying the cost of loading the full Course ORM tree
    + populate_spine_texts.
    """
    if not course_ids:
        return {}
    rows = db.query(Course.id, Course.source_locale).filter(Course.id.in_(course_ids)).all()
    by_src: dict[str, list[str]] = {}
    for cid, src in rows:
        by_src.setdefault(normalize_locale(src), []).append(str(cid))
    out: dict[str, str] = {}
    for src_locale, ids in by_src.items():
        texts = fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="course",
            entity_ids=ids,
            fields=["title"],
            display_locale=display_locale,
            source_locale=src_locale,
            fallback=fallback,
        )
        for cid in ids:
            out[cid] = texts.get((cid, "title")) or ""
    return out


def build_localized_course_summaries(
    db: Session,
    courses: list[Course],
    display_locale: LocaleCode,
) -> list[CourseSummary]:
    """Build ``CourseSummary`` for every course, resolving title +
    description against ``content_versions`` at the requested
    ``display_locale`` with per-course source_locale fallback.

    One bulk cv read covers every course (grouped by source_locale).
    Caller doesn't have to pre-populate spine texts — this function
    drives its own hydration.
    """
    if not courses:
        return []
    by_src: dict[str, list[str]] = {}
    for c in courses:
        by_src.setdefault(normalize_locale(c.source_locale), []).append(c.id)
    texts: dict[tuple[str, str], str | None] = {}
    for src_locale, ids in by_src.items():
        texts.update(
            fetch_cv_entity_texts_with_fallback(
                db,
                entity_type="course",
                entity_ids=ids,
                fields=["title", "description"],
                display_locale=display_locale,
                source_locale=src_locale,
            )
        )
    # The whole tree rides along inside every catalog card — module
    # titles, module descriptions, chapter titles — and none of it was
    # localized: it comes off the ORM, hydrated at the course's own
    # language by ``get_courses``. So an English catalog carried
    # "Модуль 1. Как узнать, что значит слово" inside every card, and so
    # did the German and Ukrainian ones.
    #
    # Found twice, by two runs of the live audit: the first pass here
    # localized titles and left descriptions, which the next run
    # promptly caught. Fields, not the field you noticed.
    tree_specs: list[tuple[str, str, str]] = []
    for course in courses:
        for module in course.modules:
            tree_specs.append(("module", str(module.id), "title"))
            tree_specs.append(("module", str(module.id), "description"))
            tree_specs.extend(("chapter", str(chapter.id), "title") for chapter in module.chapters)
    tree_texts = fetch_overlay_triples_bulk(db, tree_specs, display_locale) if tree_specs else {}

    out: list[CourseSummary] = []
    for c in courses:
        # Set runtime attrs so ``model_validate(course, from_attributes=True)``
        # picks them up via Pydantic's attribute reader.
        c.title = texts.get((c.id, "title")) or ""
        c.description = texts.get((c.id, "description"))
        summary = CourseSummary.model_validate(c, from_attributes=True)
        summary = summary.model_copy(
            update={
                "modules": [
                    module.model_copy(
                        update={
                            "title": tree_texts.get(("module", str(module.id), "title"), ""),
                            "description": tree_texts.get(("module", str(module.id), "description")),
                            "chapters": [
                                chapter.model_copy(
                                    update={"title": tree_texts.get(("chapter", str(chapter.id), "title"), "")}
                                )
                                for chapter in module.chapters
                            ],
                        }
                    )
                    for module in summary.modules
                ]
            }
        )
        out.append(summary)
    return out


def build_localized_course_dashboard_summaries(
    db: Session,
    courses: list[Course],
    display_locale: LocaleCode,
) -> list[CourseDashboardSummary]:
    """Like :func:`build_localized_course_summaries` but emits the slim
    ``CourseDashboardSummary`` (no ``modules``) for ``/users/me/courses``.

    Resolves only the course-level title + description against
    ``content_versions``; never touches the module/chapter relationship, so
    serialising the result triggers no lazy-load on a tree-less course.
    """
    if not courses:
        return []
    by_src: dict[str, list[str]] = {}
    for c in courses:
        by_src.setdefault(normalize_locale(c.source_locale), []).append(c.id)
    texts: dict[tuple[str, str], str | None] = {}
    for src_locale, ids in by_src.items():
        texts.update(
            fetch_cv_entity_texts_with_fallback(
                db,
                entity_type="course",
                entity_ids=ids,
                fields=["title", "description"],
                display_locale=display_locale,
                source_locale=src_locale,
            )
        )
    out: list[CourseDashboardSummary] = []
    for c in courses:
        c.title = texts.get((c.id, "title")) or ""
        c.description = texts.get((c.id, "description"))
        out.append(CourseDashboardSummary.model_validate(c, from_attributes=True))
    return out


def populate_spine_texts(
    db: Session,
    courses: list[Course],
    *,
    display_locale: LocaleCode | None = None,
    hydrate_modules: bool = True,
) -> None:
    """Phase 5g: ``courses.title|description`` and ``modules.title|description``
    columns dropped. Hydrate each course (and every loaded module/chapter
    title via the module list) with runtime attributes pulled from cv,
    so downstream serialization that reads ``course.title`` / ``module.title``
    keeps working unchanged.

    By default the hydration uses each course's declared ``source_locale``
    as the display_locale — that's the right choice for write paths (audit
    logs, archive snapshots, clone) and for editor surfaces that want
    source text. Pass ``display_locale`` explicitly when the caller wants
    a locale overlay (e.g. ``Accept-Language`` on a student or
    teacher-analytics read).

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
                display_locale=display_locale or src_locale,
                source_locale=src_locale,
            )
        )
    for c in courses:
        # Only overwrite an existing runtime value when cv actually has a
        # row — keeps test fixtures that pre-attach title/description for
        # entities they haven't seeded in cv from being silently wiped.
        cv_title = course_texts.get((c.id, "title"))
        if cv_title is not None:
            c.title = cv_title
        elif not hasattr(c, "title"):
            c.title = ""
        cv_desc = course_texts.get((c.id, "description"))
        if cv_desc is not None:
            c.description = cv_desc
        elif not hasattr(c, "description"):
            c.description = None

    # ── modules (every module attached to every course, grouped by the
    # parent course's source_locale so one bulk cv query covers each tier).
    # ``c.modules`` triggers SA's lazy-load if the relationship hasn't been
    # eager-fetched yet; the readiness service relies on that. The dashboard
    # list (``/users/me/courses``) loads courses with NO module tree and only
    # needs course-level text, so it passes ``hydrate_modules=False`` to skip
    # this block and avoid an N+1 lazy-load over modules it never serialises. ──
    if not hydrate_modules:
        return
    modules_by_src: dict[str, list[Module]] = {}
    for c in courses:
        mods = list(c.modules)
        if not mods:
            continue
        src = normalize_locale(c.source_locale)
        modules_by_src.setdefault(src, []).extend(mods)
    for src_locale, mods in modules_by_src.items():
        if not mods:
            continue
        bulk = fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="module",
            entity_ids=[str(m.id) for m in mods],
            fields=["title", "description"],
            display_locale=display_locale or src_locale,
            source_locale=src_locale,
        )
        for m in mods:
            cv_t = bulk.get((str(m.id), "title"))
            if cv_t is not None:
                m.title = cv_t
            elif not hasattr(m, "title"):
                m.title = ""
            cv_d = bulk.get((str(m.id), "description"))
            if cv_d is not None:
                m.description = cv_d
            elif not hasattr(m, "description"):
                m.description = None


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
        cv_t = bulk.get((str(m.id), "title"))
        if cv_t is not None:
            m.title = cv_t
        elif not hasattr(m, "title"):
            m.title = ""
        cv_d = bulk.get((str(m.id), "description"))
        if cv_d is not None:
            m.description = cv_d
        elif not hasattr(m, "description"):
            m.description = None


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

    # Nothing translated for this locale.
    #
    # Where nothing translates, there is only one language, and serving the
    # text that exists is not substituting a language for the reader's — it
    # is the only language on the platform. Local development, CI, a deploy
    # without a provider key.
    if not is_translation_enabled():
        return base

    # Text that carries no language at all — "OK", "2026", "Genesis", a
    # person's name — is the same string in every language we serve, so it is
    # served to everyone. Note the question: not "which language is this"
    # but "is this in a language". A detector that cannot name the language
    # of a Ukrainian sentence has not shown the sentence to be neutral.
    if not carries_language(base):
        return base

    # Otherwise the base text IS in a language, and it is not this reader's.
    #
    # This used to serve it anyway. That reads as helpful and is not: it
    # decides for the reader that some language beats nothing, and decides it
    # silently. A Ukrainian student would open a lesson, find Russian, and
    # have nothing telling them the platform simply had not translated it
    # yet. There is no principal language here and no spare one; what a
    # person sees follows from what they chose.
    #
    # ``None`` means "not in your language", and the surface above decides
    # how to say so. It is not a common state: a course cannot enter the
    # catalog until every language has it (``translation/completeness.py``),
    # so a reader meets this in the gap between a teacher posting an
    # announcement and the worker translating it.
    return None


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


def build_localized_course_response_with_tree(
    db: Session,
    course: Course,
    display_locale: LocaleCode,
) -> CourseResponse:
    """Localized course title/description plus module and chapter titles for students.

    Every title resolves to ``""`` when this language does not have one.
    It used to fall back to ``mod.title`` — the source column, in the
    author's language — which is how a German reader opening a Russian
    course got the whole tree in Russian: module names, lesson names,
    the course title itself. ``pick`` was doing its job and returning
    ``None``; the ``or`` after it put the other language straight back.

    An empty string is what the reader-facing clients already know how
    to render: ``orNotTranslated`` in the web app turns it into "not
    translated yet". A course nobody has translated is not a course in
    that language, and saying so is the whole point of not having a
    spare one.
    """
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

    # Build the response bottom-up in a SINGLE validation pass. The previous
    # implementation validated every chapter/module twice — once to build the
    # localized ``new_*`` lists (model_validate + model_copy), then again in a
    # final ``CourseResponse.model_validate(course)`` that re-cascaded the whole
    # ORM tree only to have its modules thrown away by a ``model_copy``. On a
    # 240-chapter course that doubled the Pydantic work. Constructing each model
    # directly (Pydantic still validates on construction) validates every entity
    # exactly once. NB: ``chapter.title`` is a real column (bilingual source
    # storage) so we must NOT write the display title back onto the ORM object —
    # we only read ``ch.title`` as the fallback and pass the localized value into
    # a fresh ``ChapterResponse``. The field lists below mirror
    # CourseResponse / ModuleResponse / ChapterResponse; the no-overlay parity
    # test in test_courses_bilingual_source guards against drift.
    # ``model_validate(dict)`` validates each entity once; nested already-built
    # ChapterResponse / ModuleResponse instances are accepted as-is (Pydantic v2
    # ``revalidate_instances='never'``), so there's no re-cascade. Using a dict
    # (rather than kwargs) keeps the ORM's wider column types — ``str`` for the
    # ``chapter_type`` / ``access_mode`` Literals — validating at runtime without
    # tripping the static type checker.
    new_modules: list[ModuleResponse] = []
    for mod in course.modules:
        mt = loc.pick("module", str(mod.id), "title", mod.title)
        md = loc.pick("module", str(mod.id), "description", mod.description)
        new_chapters = [
            ChapterResponse.model_validate(
                {
                    "id": str(ch.id),
                    "module_id": str(ch.module_id),
                    "title": loc.pick("chapter", str(ch.id), "title", ch.title) or "",
                    "order_index": ch.order_index,
                    "chapter_type": ch.chapter_type or "reading",
                    "requires_completion": ch.requires_completion,
                    "is_locked": ch.is_locked,
                }
            )
            for ch in mod.chapters
        ]
        new_modules.append(
            ModuleResponse.model_validate(
                {
                    "id": str(mod.id),
                    "course_id": str(mod.course_id),
                    "title": mt or "",
                    "description": md,
                    "order_index": mod.order_index,
                    "due_date": mod.due_date,
                    "chapters": new_chapters,
                }
            )
        )

    return CourseResponse.model_validate(
        {
            "id": course.id,
            "title": loc.pick("course", course.id, "title", course.title) or "",
            "description": loc.pick("course", course.id, "description", course.description),
            "image_url": course.image_url,
            "status": course.status,
            "access_mode": course.access_mode,
            "created_by": course.created_by,
            "created_at": course.created_at,
            "updated_at": course.updated_at,
            "deleted_at": course.deleted_at,
            "enrollment_start": course.enrollment_start,
            "enrollment_end": course.enrollment_end,
            "modules": new_modules,
        }
    )


def _fetch_quiz_tree_texts(
    db: Session,
    quiz: Quiz,
    *,
    display_locale: LocaleCode,
    source_locale: LocaleCode,
    prefer_human: bool = False,
) -> tuple[dict[tuple[str, str], str | None], dict[tuple[str, str], str | None], dict[tuple[str, str], str | None]]:
    """Bulk-fetch every cv text for ``quiz`` + its questions + their options
    at display→source→any locale fallback. Returns three (entity_id, field)
    → text dicts so callers can build whichever response shape they need.

    Phase 5f: ``quizzes.title``, ``quizzes.description``,
    ``quiz_questions.question_text`` and ``quiz_options.option_text``
    were dropped, so cv is the only store. Three calls (one per
    entity_type) keeps the SQL tuple-IN clauses simple and lets each
    use its own ``fields=[]`` list.

    ``prefer_human`` flows down into ``fetch_cv_entity_texts_with_fallback``
    so the teacher editor (``?source=1``) prefers human rows in the
    any-locale tier. See ``read.fetch_cv_entity_texts_with_fallback`` for
    the semantics.
    """
    quiz_texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="quiz",
        entity_ids=[str(quiz.id)],
        fields=["title", "description"],
        display_locale=display_locale,
        source_locale=source_locale,
        prefer_human=prefer_human,
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
            prefer_human=prefer_human,
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
            prefer_human=prefer_human,
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
    prefer_human: bool = False,
) -> QuizStudentResponse:
    """Phase 5f: quiz tree text columns dropped — fetch every title /
    description / question_text / option_text from cv with three-tier
    fallback, then assemble the student-facing response.
    """
    quiz_texts, question_texts, option_texts = _fetch_quiz_tree_texts(
        db, quiz, display_locale=display_locale, source_locale=source_locale, prefer_human=prefer_human
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
    create / update / source=1 list routes. Always prefers human-origin
    rows in the any-locale tier — a teacher edit surface should never
    surface MT output even if a localised MT row was created earlier.
    """
    quiz_texts, question_texts, option_texts = _fetch_quiz_tree_texts(
        db, quiz, display_locale=source_locale, source_locale=source_locale, prefer_human=True
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
    prefer_human: bool = False,
) -> list[AssignmentResponse]:
    """Phase 5e3: ``assignments.title`` + ``description`` columns dropped.
    Both texts live in ``content_versions`` now. Resolve each via a
    three-tier fallback (display → source → any-locale).
    """
    if not assignments:
        return []
    ids = [str(a.id) for a in assignments]
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="assignment",
        entity_ids=ids,
        fields=["title", "description"],
        display_locale=display_locale,
        source_locale=source_locale,
        prefer_human=prefer_human,
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
    prefer_human: bool = False,
    fallback: Literal["auto", "none", "source_then_any"] = "auto",
) -> list[BlockResponse]:
    """Apply stored translations to TipTap HTML stored on chapter blocks.

    Phase 5e2: the legacy ``content`` column was dropped. Both the
    source text and the localised overlay live in ``content_versions``
    now. Build the response manually because ``model_validate(block)``
    would try to read ``block.content`` (no longer an attribute).

    ``fallback`` decides what a missing translation means, and this is
    the lesson body — the longest thing anybody reads on the platform.

    * ``"none"`` (what a reader gets where the platform translates):
      the block comes back empty rather than in somebody else's
      language. The chapter view renders that as "not translated yet".
    * ``"source_then_any"``: display → source → any locale. For the
      people who must see the text whatever language it is in — the
      teacher editing their own lesson, the ``?source=1`` view.
    * ``"auto"`` (default): ``"none"`` where the platform translates,
      ``"source_then_any"`` where it does not.

    The three-tier chain used to be unconditional, which is how a
    German student reading a Russian course got the whole lesson in
    Russian while every title around it correctly said the course was
    not available in German.

    When ``prefer_human`` is set, the any-locale tier prefers
    human-authored rows over MT ones — used by the ``?source=1`` editor
    view so a teacher never sees a stale MT row as the "source" content
    for a block whose source-locale row went missing.
    """
    if fallback == "auto":
        fallback = "none" if is_translation_enabled() else "source_then_any"
    if not blocks:
        return []
    block_ids = [str(b.id) for b in blocks]
    # All-locale bulk fetch: one indexed query covers display + source
    # + any-locale tiers. Ordered by created_at so we deterministically
    # pick the earliest if multiple rows exist per block at a locale.
    rows = (
        db.query(ContentVersion.entity_id, ContentVersion.locale, ContentVersion.text, ContentVersion.origin)
        .filter(
            ContentVersion.entity_type == "chapter_block",
            ContentVersion.entity_id.in_(block_ids),
            ContentVersion.field == "content",
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == ContentVersionStatus.OK,
        )
        .order_by(ContentVersion.entity_id, ContentVersion.created_at)
        .all()
    )
    by_block_locale: dict[tuple[str, str], str] = {}
    any_by_block: dict[str, str] = {}
    human_by_block: dict[str, str] = {}
    for eid, locale, text, origin in rows:
        by_block_locale.setdefault((eid, locale), text)
        any_by_block.setdefault(eid, text)
        if origin == "human":
            human_by_block.setdefault(eid, text)
    out: list[BlockResponse] = []
    for b in blocks:
        bid = str(b.id)
        content = by_block_locale.get((bid, display_locale))
        if content is None and fallback == "source_then_any":
            any_tier = human_by_block.get(bid) or any_by_block.get(bid) if prefer_human else any_by_block.get(bid)
            content = by_block_locale.get((bid, source_locale)) or any_tier
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

    mt = loc.pick("module", str(module.id), "title", module.title) or ""
    md = loc.pick("module", str(module.id), "description", module.description)
    new_chapters: list[ChapterResponse] = []
    for ch in module.chapters:
        cht = loc.pick("chapter", str(ch.id), "title", ch.title) or ""
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
    prefer_human: bool = False,
) -> list[AnnouncementResponse]:
    """Phase 5e5: ``announcements.title`` + ``content`` columns dropped.
    Both texts live in cv now. Resolve each via the three-tier fallback
    (display → source → any-locale).
    """
    if not announcements:
        return []
    ids = [str(a.id) for a in announcements]
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="announcement",
        entity_ids=ids,
        fields=["title", "content"],
        display_locale=display_locale,
        source_locale=source_locale,
        prefer_human=prefer_human,
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
    prefer_human: bool = False,
) -> list[CourseEventResponse]:
    """Phase 5e4: ``course_events.title`` + ``description`` columns dropped.
    Both texts live in cv now. Resolve each via the three-tier
    fallback (display → source → any-locale).
    """
    if not events:
        return []
    ids = [str(e.id) for e in events]
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course_event",
        entity_ids=ids,
        fields=["title", "description"],
        display_locale=display_locale,
        source_locale=source_locale,
        prefer_human=prefer_human,
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
    "build_localized_course_response_with_tree",
    "build_localized_course_summaries",
    "build_localized_module_response",
    "build_localized_quiz_student_response",
    "fetch_course_titles_by_id",
    "fetch_overlay_triples_bulk",
    "localize_announcement_rows",
    "localize_assignment_rows",
    "localize_chapter_block_rows",
    "localize_course_event_rows",
    "pick_overlay_value",
    "should_apply_course_translation_overlay",
]
