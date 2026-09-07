"""Course readiness checklist.

Runs a fixed catalog of structural and content checks against a course
and returns one ``ReadinessReport``. The frontend uses this to:

  * surface a "publish-ready or not" indicator on the course editor;
  * itemize what's missing (with deep-link metadata so each failing
    check can be one-click navigated to its fix);
  * gate ``draft -> published`` transitions behind a confirm dialog
    when any *critical* check fails.

Every message is identified by an i18n key — never a translated string
in the backend response — so EN and RU render natively without the
service ever caring about locale.

Severities:

* ``critical``    — failing means the published course would actually
                    break for students (no lessons at all, a blank
                    reading, a quiz with no questions). Triggers a
                    confirm dialog on publish; never hard-blocks.
* ``recommended`` — failing means a noticeably incomplete catalog
                    listing (no description, no cover image).
* ``polish``      — small quality signals (an empty module, ≥ 2 modules,
                    full grading weights). Always informational.

What is *structurally* required is a chapter, not a module. A course
is a set of lessons; a module is an optional heading over some of them.
An empty heading is untidy — ``polish`` — and it stopped being a reason
a course cannot go out on 2026-09-07, after the first teacher to use
this checklist invented modules his four-lesson course did not need and
then could not publish behind the empty ones he was left with.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session, joinedload

from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock

# ``Chapter`` is used at runtime by the helper functions below
# (``_make_chapter_subject`` / ``_open_chapter_action`` read attributes
# off real Chapter instances). ``Course`` is the argument type of the
# public entry point ``compute_readiness`` — runtime SQLAlchemy ORM
# instance is passed in. Both legitimately live at runtime, not just
# in annotations.
from app.models.course import Chapter, Course  # noqa: TC001
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.services.course_structure import build_spine
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.resolve_for_display import populate_spine_texts

Severity = Literal["critical", "recommended", "polish"]

# ─── Subject + action vocabularies ──────────────────────────────────────
# Kept as ``Literal`` aliases so the schema layer mirrors them in
# Pydantic and the frontend gets exhaustive ``switch`` branches.
SubjectType = Literal["course", "module", "chapter", "quiz", "assignment"]
ActionType = Literal[
    "set_description",
    "set_cover_image",
    "open_enrollment",
    "add_module",
    "open_module",
    "open_chapter",
    "open_quiz",
    "open_assignment",
    "open_grading_weights",
]


@dataclass(frozen=True)
class ReadinessSubject:
    type: SubjectType
    id: str
    title: str


@dataclass(frozen=True)
class ReadinessAction:
    type: ActionType
    # Free-form parameters carrying IDs the frontend needs to navigate.
    # Kept generic so a single ``{ module_id, chapter_id }`` payload
    # works for any action without subclassing.
    params: dict[str, str]


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    severity: Severity
    passed: bool
    message_key: str
    # Some checks (e.g. "course has description") affect the course as a
    # whole; others (e.g. "Chapter X is missing content") name a specific
    # entity. The latter populate ``subject``; both can populate
    # ``action`` so the UI knows how to deep-link to a fix.
    subject: ReadinessSubject | None = None
    action: ReadinessAction | None = None


@dataclass(frozen=True)
class ReadinessReport:
    course_id: str
    total: int
    passing: int
    critical_failing: int
    score: int
    """Percent (0-100) of all checks passing. Useful for a single
    summary number on the dashboard pill."""

    checks: tuple[ReadinessCheck, ...]


# ─── Internal helpers ───────────────────────────────────────────────────


def _has_meaningful_content(block: ChapterBlock, blocks_with_cv_content: set[str]) -> bool:
    """A reading block 'has content' if its body isn't blank. Quiz /
    assignment blocks aren't counted here — those chapters are validated
    by their own checks (``quiz has questions``, etc.) so a chapter
    consisting only of a quiz block still passes the content rule.

    The ``content`` column was dropped. The caller pre-fetches
    a set of block ids that have an active cv content row at any locale
    (``_fetch_blocks_with_cv_content``); we just consult the set here.
    """
    if block.block_type not in {"text", "html", "video", "image", "file"}:
        return False
    if block.block_type == "file":
        return bool(block.file_path)
    return str(block.id) in blocks_with_cv_content


def _question_is_complete(question: QuizQuestion, options: list[QuizOption]) -> bool:
    """A quiz question is publishable when:

    * ``multiple_choice`` — at least 2 options and at least 1 marked correct.
    * ``true_false``     — exactly 2 options with exactly 1 marked correct.
    * ``short_answer`` / ``essay`` — no options needed (grader-driven).

    Unknown question types are treated as valid; the schema layer is the
    authoritative gate on which types are allowed.
    """
    qtype = question.question_type
    if qtype == "multiple_choice":
        return len(options) >= 2 and any(o.is_correct for o in options)
    if qtype == "true_false":
        return len(options) == 2 and sum(1 for o in options if o.is_correct) == 1
    return True


def _make_chapter_subject(chapter: Chapter) -> ReadinessSubject:
    return ReadinessSubject(type="chapter", id=chapter.id, title=chapter.title or "")


def _chapter_link_params(chapter: Chapter) -> dict[str, str]:
    """``{module_id, chapter_id}`` for the deep link — ``module_id`` only
    while the chapter has one. Every chapter does today; the key is
    conditional so the model's optional ``module_id`` has one honest
    reading here instead of an empty string."""
    params = {"chapter_id": chapter.id}
    if chapter.module_id is not None:
        params["module_id"] = chapter.module_id
    return params


def _open_chapter_action(chapter: Chapter) -> ReadinessAction:
    return ReadinessAction(type="open_chapter", params=_chapter_link_params(chapter))


def _open_quiz_action(chapter: Chapter) -> ReadinessAction:
    return ReadinessAction(type="open_quiz", params=_chapter_link_params(chapter))


def _open_assignment_action(chapter: Chapter) -> ReadinessAction:
    return ReadinessAction(type="open_assignment", params=_chapter_link_params(chapter))


# ─── Main entry point ───────────────────────────────────────────────────


def compute_readiness(db: Session, course: Course) -> ReadinessReport:
    """Run every readiness check against ``course`` and return a report.

    The caller is responsible for permission gating; this function does
    no auth. It also assumes the caller eagerly loaded the course's
    modules *and* its chapters (``_COURSE_TREE`` does both) — otherwise
    we'd run a fresh query for them here.

    Hydrates ``course.title`` / ``course.description`` and each loaded
    ``module.title`` from ``content_versions`` before running checks so
    the rules can read them as plain attributes.
    """
    populate_spine_texts(db, [course])
    checks: list[ReadinessCheck] = []

    # ── Course-level checks (recommended / polish) ───────────────────
    checks.append(
        ReadinessCheck(
            id="has_description",
            severity="recommended",
            passed=bool((course.description or "").strip()),
            message_key="courseReadiness.checks.hasDescription",
            action=ReadinessAction(type="set_description", params={}),
        )
    )
    checks.append(
        ReadinessCheck(
            id="has_cover_image",
            severity="recommended",
            passed=bool((course.image_url or "").strip()),
            message_key="courseReadiness.checks.hasCoverImage",
            action=ReadinessAction(type="set_cover_image", params={}),
        )
    )

    # Every language, or the course does not go out. This is the only
    # check here the teacher cannot act on directly — no deep link,
    # because there is nothing for them to fix. It is either still
    # running, or a translation needs a person to look at it.
    completeness = course_translation_completeness(db, course)
    checks.append(
        ReadinessCheck(
            id="translations_complete",
            severity="critical",
            passed=completeness.is_complete,
            message_key="courseReadiness.checks.translationsComplete",
        )
    )

    # Enrollment window only matters for ``public`` access mode — the
    # ``institute`` flow puts students into cohorts directly. Skip the
    # check entirely for institute courses rather than reporting a
    # green-tick that's misleading.
    if course.access_mode == "public":
        checks.append(
            ReadinessCheck(
                id="has_enrollment_window",
                severity="recommended",
                passed=course.enrollment_start is not None and course.enrollment_end is not None,
                message_key="courseReadiness.checks.hasEnrollmentWindow",
                action=ReadinessAction(type="open_enrollment", params={}),
            )
        )

    # ── Structure (critical) ─────────────────────────────────────────
    # What a course must have to be worth opening is a lesson, not a
    # heading. Read the chapters off the course itself: a chapter belongs
    # to its course, and the module — when there is one — only groups it.
    active_modules = [m for m in course.modules if m.deleted_at is None]
    # Through the shared spine so the checklist lists lessons in the order
    # the course reads them, headings included, instead of interleaving
    # modules by an ``order_index`` that still counts per module.
    active_chapters = list(build_spine(active_modules, [c for c in course.chapters if c.deleted_at is None]).chapters)

    # No deep-link action on purpose. "Add a module" is the wrong offer
    # now — it is what pushed the first teacher into inventing modules
    # for a four-lesson course — and there is no "add chapter" action for
    # the editor to answer yet. Step 5 gives this check its button.
    checks.append(
        ReadinessCheck(
            id="has_at_least_one_chapter",
            severity="critical",
            passed=bool(active_chapters),
            message_key="courseReadiness.checks.hasAtLeastOneChapter",
        )
    )

    # Polish, and only for a course that groups its lessons at all. In a
    # course with no modules "the course has only one module" is not a
    # remark anybody can act on — it is a nudge back towards the very
    # structure this model stopped requiring.
    if active_modules:
        checks.append(
            ReadinessCheck(
                id="has_multiple_modules",
                severity="polish",
                passed=len(active_modules) >= 2,
                message_key="courseReadiness.checks.hasMultipleModules",
            )
        )

    # ── Per-module: chapters exist (polish) ──────────────────────────
    # An empty module is untidy, not broken: its course still opens and
    # every lesson in it still reads. This was ``critical`` until the
    # model moved, and it is the exact rule that left a live teacher's
    # four-lesson course unpublishable behind a heading he only made
    # because the old checklist demanded one.
    for module in active_modules:
        module_chapters = [c for c in module.chapters if c.deleted_at is None]
        checks.append(
            ReadinessCheck(
                id=f"module_has_chapters:{module.id}",
                severity="polish",
                passed=bool(module_chapters),
                message_key="courseReadiness.checks.moduleHasChapters",
                subject=ReadinessSubject(type="module", id=module.id, title=module.title or ""),
                action=ReadinessAction(type="open_module", params={"module_id": module.id}),
            )
        )

    # ── Per-chapter content checks ───────────────────────────────────
    # Load blocks + quizzes + assignments in one round-trip so a course
    # with 50 chapters doesn't issue 50 separate fetches.
    #
    # Walked from the course, not from the modules: a chapter outside
    # every module used to be invisible here, so a course whose only
    # reading chapter is empty sailed through the publish gate with a
    # clean checklist and shipped a blank page to students.
    all_chapter_ids = [c.id for c in active_chapters]
    blocks_by_chapter: dict[str, list[ChapterBlock]] = {cid: [] for cid in all_chapter_ids}
    if all_chapter_ids:
        for block in db.query(ChapterBlock).filter(ChapterBlock.chapter_id.in_(all_chapter_ids)).all():
            blocks_by_chapter.setdefault(block.chapter_id, []).append(block)

    # ``chapter_blocks.content`` column dropped. Pre-fetch the
    # set of block ids that have at least one active+ok cv content row
    # at any locale so the readiness check can answer "block has content?"
    # in O(1) per block via ``_has_meaningful_content``.
    all_block_ids = [str(b.id) for blocks in blocks_by_chapter.values() for b in blocks]
    blocks_with_cv_content: set[str] = set()
    if all_block_ids:
        from app.models.content_version import ContentVersion, ContentVersionStatus

        # Filter out blank/whitespace text in Python — keeps the SQL
        # portable across SQLite (tests) and Postgres (prod). Pre-5e2
        # behaviour treated whitespace-only ``content`` as missing, so
        # we preserve that semantics on top of the cv backing store.
        blocks_with_cv_content = {
            eid
            for (eid, text) in db.query(ContentVersion.entity_id, ContentVersion.text)
            .filter(
                ContentVersion.entity_type == "chapter_block",
                ContentVersion.entity_id.in_(all_block_ids),
                ContentVersion.field == "content",
                ContentVersion.superseded_by.is_(None),
                ContentVersion.status == ContentVersionStatus.OK,
            )
            .all()
            if text and text.strip()
        }

    # Quizzes / assignments are looked up by chapter_id; eagerly load
    # quiz.questions + their options so we can validate each question.
    quizzes_by_chapter: dict[str, Quiz] = {}
    if all_chapter_ids:
        for loaded_quiz in (
            db.query(Quiz)
            .options(joinedload(Quiz.questions).joinedload(QuizQuestion.options))
            .filter(Quiz.chapter_id.in_(all_chapter_ids))
            .all()
        ):
            quizzes_by_chapter[loaded_quiz.chapter_id] = loaded_quiz

    assignments_by_chapter: dict[str, Assignment] = {}
    if all_chapter_ids:
        for loaded_assignment in db.query(Assignment).filter(Assignment.chapter_id.in_(all_chapter_ids)).all():
            assignments_by_chapter[loaded_assignment.chapter_id] = loaded_assignment

    # ``assignments.description`` column dropped. Bulk-fetch
    # the set of assignment ids with a non-blank cv description row at
    # any locale (same pattern as ``blocks_with_cv_content`` above) so
    # the per-chapter check can answer "has brief?" in O(1).
    assignments_with_cv_brief: set[str] = set()
    if assignments_by_chapter:
        from app.models.content_version import ContentVersion, ContentVersionStatus

        assignment_ids = [str(a.id) for a in assignments_by_chapter.values()]
        assignments_with_cv_brief = {
            eid
            for (eid, text) in db.query(ContentVersion.entity_id, ContentVersion.text)
            .filter(
                ContentVersion.entity_type == "assignment",
                ContentVersion.entity_id.in_(assignment_ids),
                ContentVersion.field == "description",
                ContentVersion.superseded_by.is_(None),
                ContentVersion.status == ContentVersionStatus.OK,
            )
            .all()
            if text and text.strip()
        }

    has_any_quiz_chapter = False
    has_any_assignment_chapter = False

    # Same list the structural check counted — every live chapter of the
    # course, grouped or not, each one exactly once.
    for chapter in active_chapters:
        ctype = chapter.chapter_type or "reading"

        if ctype == "reading":
            blocks = blocks_by_chapter.get(chapter.id, [])
            checks.append(
                ReadinessCheck(
                    id=f"reading_has_content:{chapter.id}",
                    severity="critical",
                    passed=any(_has_meaningful_content(b, blocks_with_cv_content) for b in blocks),
                    message_key="courseReadiness.checks.readingHasContent",
                    subject=_make_chapter_subject(chapter),
                    action=_open_chapter_action(chapter),
                )
            )

        elif ctype in {"quiz", "exam"}:
            has_any_quiz_chapter = True
            quiz = quizzes_by_chapter.get(chapter.id)
            has_question = quiz is not None and any(quiz.questions)
            checks.append(
                ReadinessCheck(
                    id=f"quiz_has_question:{chapter.id}",
                    severity="critical",
                    passed=has_question,
                    message_key=(
                        "courseReadiness.checks.examHasQuestion"
                        if ctype == "exam"
                        else "courseReadiness.checks.quizHasQuestion"
                    ),
                    subject=_make_chapter_subject(chapter),
                    action=_open_quiz_action(chapter),
                )
            )
            if quiz is not None:
                bad_questions = [q for q in quiz.questions if not _question_is_complete(q, list(q.options))]
                checks.append(
                    ReadinessCheck(
                        id=f"quiz_questions_complete:{chapter.id}",
                        severity="critical",
                        passed=not bad_questions,
                        message_key="courseReadiness.checks.quizQuestionsComplete",
                        subject=_make_chapter_subject(chapter),
                        action=_open_quiz_action(chapter),
                    )
                )

        elif ctype == "assignment":
            has_any_assignment_chapter = True
            assignment = assignments_by_chapter.get(chapter.id)
            has_brief = assignment is not None and str(assignment.id) in assignments_with_cv_brief
            checks.append(
                ReadinessCheck(
                    id=f"assignment_has_brief:{chapter.id}",
                    severity="critical",
                    passed=has_brief,
                    message_key="courseReadiness.checks.assignmentHasBrief",
                    subject=_make_chapter_subject(chapter),
                    action=_open_assignment_action(chapter),
                )
            )

    # ── Grading weights (polish) ────────────────────────────────────
    # Since D5 there are two categories, not three: participation is pinned to
    # 0 by CHECK, so the weights are simply quiz + assignment == 100. A course
    # with quiz chapters and ``quiz_weight = 0`` is still surprising — students
    # complete quizzes that don't count — so both checks stay.
    if has_any_quiz_chapter:
        checks.append(
            ReadinessCheck(
                id="quiz_weight_nonzero",
                severity="polish",
                passed=course.quiz_weight > 0,
                message_key="courseReadiness.checks.quizWeightNonzero",
                action=ReadinessAction(type="open_grading_weights", params={}),
            )
        )
    if has_any_assignment_chapter:
        checks.append(
            ReadinessCheck(
                id="assignment_weight_nonzero",
                severity="polish",
                passed=course.assignment_weight > 0,
                message_key="courseReadiness.checks.assignmentWeightNonzero",
                action=ReadinessAction(type="open_grading_weights", params={}),
            )
        )

    # A quiz that demands more than the course does creates the trap where a
    # student passes the course on paper and never reaches progress 100: the
    # chapter stays incomplete, so the certificate stays out of reach, and
    # nothing on screen explains why (D3).
    # Compared against the real threshold, not a truncated one: a quiz at 71 in
    # a course whose line is 70.5 is above it, and int() said otherwise.
    course_line = Decimal(str(course.pass_threshold or 0))
    strict_quizzes = [q for q in quizzes_by_chapter.values() if Decimal(q.passing_score) > course_line]
    if strict_quizzes:
        checks.append(
            ReadinessCheck(
                id="quiz_threshold_above_course",
                severity="polish",
                passed=False,
                message_key="courseReadiness.checks.quizThresholdAboveCourse",
                action=ReadinessAction(type="open_grading_weights", params={}),
            )
        )

    # The mirror of the check above, and the one nobody thinks of: a course line
    # RAISED after its quizzes were written leaves every quiz easier than the
    # course. A student then clears each quiz, is told each time that they
    # passed, and still lands below the line the course grades them on — with
    # every chapter green. The first check catches drift one way; without this
    # one, drift the other way is silent.
    lenient_quizzes = [q for q in quizzes_by_chapter.values() if Decimal(q.passing_score) < course_line]
    if lenient_quizzes:
        checks.append(
            ReadinessCheck(
                id="quiz_threshold_below_course",
                severity="polish",
                passed=False,
                message_key="courseReadiness.checks.quizThresholdBelowCourse",
                action=ReadinessAction(type="open_grading_weights", params={}),
            )
        )

    # ── Aggregate ────────────────────────────────────────────────────
    total = len(checks)
    passing = sum(1 for c in checks if c.passed)
    critical_failing = sum(1 for c in checks if c.severity == "critical" and not c.passed)
    score = round((passing / total) * 100) if total > 0 else 100

    return ReadinessReport(
        course_id=course.id,
        total=total,
        passing=passing,
        critical_failing=critical_failing,
        score=score,
        checks=tuple(checks),
    )
