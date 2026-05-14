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
                    break for students (empty modules, quiz with no
                    questions, etc.). Triggers a confirm dialog on
                    publish; never hard-blocks.
* ``recommended`` — failing means a noticeably incomplete catalog
                    listing (no description, no cover image).
* ``polish``      — small quality signals (≥ 2 modules, full grading
                    weights). Always informational.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def _has_meaningful_content(block: ChapterBlock) -> bool:
    """A reading block 'has content' if its body isn't blank. Quiz /
    assignment blocks aren't counted here — those chapters are validated
    by their own checks (``quiz has questions``, etc.) so a chapter
    consisting only of a quiz block still passes the content rule."""
    if block.block_type not in {"text", "html", "video", "image", "file"}:
        return False
    if block.block_type == "file":
        return bool(block.file_path)
    if block.block_type == "video":
        return bool(block.content)
    return bool((block.content or "").strip())


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


def _open_chapter_action(chapter: Chapter) -> ReadinessAction:
    return ReadinessAction(
        type="open_chapter",
        params={"module_id": chapter.module_id, "chapter_id": chapter.id},
    )


# ─── Main entry point ───────────────────────────────────────────────────


def compute_readiness(db: Session, course: Course) -> ReadinessReport:
    """Run every readiness check against ``course`` and return a report.

    The caller is responsible for permission gating; this function does
    no auth. It also assumes the caller eagerly loaded the modules
    (otherwise we'd run a fresh query for them here).
    """
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

    # ── Modules (critical) ───────────────────────────────────────────
    active_modules = [m for m in course.modules if m.deleted_at is None]
    checks.append(
        ReadinessCheck(
            id="has_at_least_one_module",
            severity="critical",
            passed=bool(active_modules),
            message_key="courseReadiness.checks.hasAtLeastOneModule",
            action=ReadinessAction(type="add_module", params={}),
        )
    )

    # Polish: encourage at least two modules — a one-module course can
    # be valid (e.g. a single seminar) but is uncommon.
    checks.append(
        ReadinessCheck(
            id="has_multiple_modules",
            severity="polish",
            passed=len(active_modules) >= 2,
            message_key="courseReadiness.checks.hasMultipleModules",
        )
    )

    # ── Per-module: chapters exist (critical) ────────────────────────
    for module in active_modules:
        active_chapters = [c for c in module.chapters if c.deleted_at is None]
        checks.append(
            ReadinessCheck(
                id=f"module_has_chapters:{module.id}",
                severity="critical",
                passed=bool(active_chapters),
                message_key="courseReadiness.checks.moduleHasChapters",
                subject=ReadinessSubject(type="module", id=module.id, title=module.title or ""),
                action=ReadinessAction(type="open_module", params={"module_id": module.id}),
            )
        )

    # ── Per-chapter content checks ───────────────────────────────────
    # Load blocks + quizzes + assignments in one round-trip so a course
    # with 50 chapters doesn't issue 50 separate fetches.
    all_chapter_ids = [c.id for m in active_modules for c in m.chapters if c.deleted_at is None]
    blocks_by_chapter: dict[str, list[ChapterBlock]] = {cid: [] for cid in all_chapter_ids}
    if all_chapter_ids:
        for block in db.query(ChapterBlock).filter(ChapterBlock.chapter_id.in_(all_chapter_ids)).all():
            blocks_by_chapter.setdefault(block.chapter_id, []).append(block)

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

    has_any_quiz_chapter = False
    has_any_assignment_chapter = False

    for module in active_modules:
        for chapter in (c for c in module.chapters if c.deleted_at is None):
            ctype = chapter.chapter_type or "reading"

            if ctype == "reading":
                blocks = blocks_by_chapter.get(chapter.id, [])
                checks.append(
                    ReadinessCheck(
                        id=f"reading_has_content:{chapter.id}",
                        severity="critical",
                        passed=any(_has_meaningful_content(b) for b in blocks),
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
                        action=ReadinessAction(
                            type="open_quiz",
                            params={"module_id": chapter.module_id, "chapter_id": chapter.id},
                        ),
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
                            action=ReadinessAction(
                                type="open_quiz",
                                params={"module_id": chapter.module_id, "chapter_id": chapter.id},
                            ),
                        )
                    )

            elif ctype == "assignment":
                has_any_assignment_chapter = True
                assignment = assignments_by_chapter.get(chapter.id)
                checks.append(
                    ReadinessCheck(
                        id=f"assignment_has_brief:{chapter.id}",
                        severity="critical",
                        passed=assignment is not None and bool((assignment.description or "").strip()),
                        message_key="courseReadiness.checks.assignmentHasBrief",
                        subject=_make_chapter_subject(chapter),
                        action=ReadinessAction(
                            type="open_assignment",
                            params={"module_id": chapter.module_id, "chapter_id": chapter.id},
                        ),
                    )
                )

    # ── Grading weights (polish) ────────────────────────────────────
    # The DB CHECK guarantees ``quiz + assignment + participation == 100``
    # but a course with quiz chapters and ``quiz_weight = 0`` is
    # surprising: students complete quizzes that don't count. Flag it.
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
