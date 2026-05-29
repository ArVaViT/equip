"""Deep clone of a course tree (modules, chapters, blocks, quizzes, assignments)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion

from ._queries import _COURSE_TREE

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Per-entity fields whose cv text rows the clone copies across. Mirrors
# the ``REGISTRY`` translatable-fields list in
# ``app/services/translation/registry.py`` — adding a translatable field
# means adding it here too, otherwise clones land text-less in that
# field. The CI registry-drift guard would catch a missed addition.
_CLONABLE_TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "course": ("title", "description"),
    "module": ("title", "description"),
    "chapter": ("title",),
    "chapter_block": ("content",),
    "quiz": ("title", "description"),
    "quiz_question": ("question_text",),
    "quiz_option": ("option_text",),
    "assignment": ("title", "description"),
}


def _clone_cv_rows(
    db: Session,
    *,
    entity_type: str,
    id_map: dict[str, str],
    fields: tuple[str, ...],
) -> None:
    """Copy every active+ok ``content_versions`` row from the old entity
    ids to the new ones, preserving locale + origin so the clone keeps
    its bilingual coverage. ``id_map`` maps ``str(old_entity_id) ->
    str(new_entity_id)``. Failed / failed_permanent rows are skipped —
    a clone deserves a fresh retry, not the prior failure's blocker.
    """
    if not id_map:
        return
    rows = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id.in_(list(id_map.keys())),
            ContentVersion.field.in_(fields),
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == "ok",
        )
        .all()
    )
    for r in rows:
        new_eid = id_map.get(str(r.entity_id))
        if new_eid is None:
            continue
        db.add(
            ContentVersion(
                id=uuid.uuid4(),
                entity_type=entity_type,
                entity_id=new_eid,
                field=r.field,
                locale=r.locale,
                text=r.text,
                origin=r.origin,
                status="ok",
                source_locale=r.source_locale,
                source_hash=r.source_hash,
                # source_version_id intentionally NOT carried — pointing
                # the clone's MT row at the original's source row would
                # cascade-invalidate the clone when the original
                # changes; clones should be independent post-fork.
            )
        )


def clone_course(db: Session, course_id: str, teacher_id: str | uuid.UUID) -> Course | None:
    """Deep-clone a course and all nested content. Returns the new Course.

    Copies: Course -> Modules -> Chapters -> ChapterBlocks, Quizzes
    (with questions + options), Assignments.
    ChapterBlock.quiz_id / assignment_id are remapped to the cloned entities.
    Enrollments, progress, grades, submissions, and certificates are NOT copied.
    """
    # Only clone live courses. Attempting to clone a trashed course should
    # 404 (mirrors the API-level visibility rules in get_course()).
    original = (
        db.query(Course).options(*_COURSE_TREE).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    )
    if original is None:
        return None

    all_chapter_ids = [ch.id for mod in original.modules for ch in mod.chapters]
    if not all_chapter_ids:
        all_quizzes: list[Quiz] = []
        all_questions: list[QuizQuestion] = []
        all_options: list[QuizOption] = []
        all_assignments: list[Assignment] = []
        all_blocks: list[ChapterBlock] = []
    else:
        all_quizzes = db.query(Quiz).filter(Quiz.chapter_id.in_(all_chapter_ids)).all()
        all_quiz_ids = [q.id for q in all_quizzes]

        all_questions = (
            db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(all_quiz_ids)).all() if all_quiz_ids else []
        )
        all_question_ids = [q.id for q in all_questions]

        all_options = (
            db.query(QuizOption).filter(QuizOption.question_id.in_(all_question_ids)).all() if all_question_ids else []
        )

        all_assignments = db.query(Assignment).filter(Assignment.chapter_id.in_(all_chapter_ids)).all()
        all_blocks = db.query(ChapterBlock).filter(ChapterBlock.chapter_id.in_(all_chapter_ids)).all()

    quizzes_by_chapter: dict[str, list[Quiz]] = defaultdict(list)
    for q in all_quizzes:
        quizzes_by_chapter[q.chapter_id].append(q)

    questions_by_quiz: dict[str, list[QuizQuestion]] = defaultdict(list)
    for qq in all_questions:
        questions_by_quiz[str(qq.quiz_id)].append(qq)

    options_by_question: dict[str, list[QuizOption]] = defaultdict(list)
    for o in all_options:
        options_by_question[str(o.question_id)].append(o)

    assignments_by_chapter: dict[str, list[Assignment]] = defaultdict(list)
    for a in all_assignments:
        assignments_by_chapter[a.chapter_id].append(a)

    blocks_by_chapter: dict[str, list[ChapterBlock]] = defaultdict(list)
    for b in all_blocks:
        blocks_by_chapter[b.chapter_id].append(b)

    # Phase 5z: track every (old_id -> new_id) so the cv-row copy at
    # the end of this function can fan a single bulk SELECT + bulk
    # INSERT per entity_type across the whole clone, rather than
    # touching cv inline at each model instantiation.
    course_id_map: dict[str, str] = {}
    module_id_map: dict[str, str] = {}
    chapter_id_map: dict[str, str] = {}
    block_id_map: dict[str, str] = {}
    quiz_id_map_cv: dict[str, str] = {}
    question_id_map_cv: dict[str, str] = {}
    option_id_map_cv: dict[str, str] = {}
    assignment_id_map_cv: dict[str, str] = {}

    new_course_id = str(uuid.uuid4())
    course_id_map[str(original.id)] = new_course_id
    new_course = Course(
        id=new_course_id,
        image_url=original.image_url,
        status=CourseStatus.DRAFT,
        source_locale=original.source_locale,
        created_by=uuid.UUID(teacher_id) if isinstance(teacher_id, str) else teacher_id,
        enrollment_start=None,
        enrollment_end=None,
    )
    db.add(new_course)

    for module in sorted(original.modules, key=lambda m: m.order_index):
        new_module_id = str(uuid.uuid4())
        module_id_map[str(module.id)] = new_module_id
        new_module = Module(
            id=new_module_id,
            course_id=new_course_id,
            order_index=module.order_index,
            due_date=module.due_date,
        )
        db.add(new_module)

        for chapter in sorted(module.chapters, key=lambda c: c.order_index):
            new_chapter_id = str(uuid.uuid4())
            chapter_id_map[str(chapter.id)] = new_chapter_id
            new_chapter = Chapter(
                id=new_chapter_id,
                module_id=new_module_id,
                # ``chapters.title`` is still a spine column (not yet
                # moved to cv-only); copy it verbatim. The cv row at
                # the same locale also gets cloned below so the bilingual
                # overlay is preserved.
                title=chapter.title,
                order_index=chapter.order_index,
                chapter_type=chapter.chapter_type,
                requires_completion=chapter.requires_completion,
                is_locked=chapter.is_locked,
            )
            db.add(new_chapter)
            # Postgres' unit-of-work topological sort handles the chapter →
            # block ordering correctly; SQLite (PRAGMA foreign_keys=ON, used
            # by tests) does not because ``ChapterBlock.chapter_id`` is a
            # plain String FK without a relationship wired through. Gate the
            # flush to the SQLite path so prod clones don't take N
            # round-trips for a cosmetic test-only safety net.
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                db.flush()

            quiz_id_map: dict[str, uuid.UUID] = {}
            assignment_id_map: dict[str, uuid.UUID] = {}

            for quiz in quizzes_by_chapter.get(chapter.id, []):
                new_quiz_id = uuid.uuid4()
                quiz_id_map[str(quiz.id)] = new_quiz_id
                quiz_id_map_cv[str(quiz.id)] = str(new_quiz_id)
                db.add(
                    Quiz(
                        id=new_quiz_id,
                        chapter_id=new_chapter_id,
                        quiz_type=quiz.quiz_type or "quiz",
                        max_attempts=quiz.max_attempts,
                        passing_score=quiz.passing_score,
                    )
                )

                for question in sorted(
                    questions_by_quiz.get(str(quiz.id), []),
                    key=lambda q: q.order_index,
                ):
                    new_question_id = uuid.uuid4()
                    question_id_map_cv[str(question.id)] = str(new_question_id)
                    db.add(
                        QuizQuestion(
                            id=new_question_id,
                            quiz_id=new_quiz_id,
                            question_type=question.question_type,
                            order_index=question.order_index,
                            points=question.points,
                            min_words=question.min_words,
                        )
                    )

                    for option in sorted(
                        options_by_question.get(str(question.id), []),
                        key=lambda o: o.order_index,
                    ):
                        new_option_id = uuid.uuid4()
                        option_id_map_cv[str(option.id)] = str(new_option_id)
                        db.add(
                            QuizOption(
                                id=new_option_id,
                                question_id=new_question_id,
                                is_correct=option.is_correct,
                                order_index=option.order_index,
                            )
                        )

            for assignment in assignments_by_chapter.get(chapter.id, []):
                new_assignment_id = uuid.uuid4()
                assignment_id_map[str(assignment.id)] = new_assignment_id
                assignment_id_map_cv[str(assignment.id)] = str(new_assignment_id)
                db.add(
                    Assignment(
                        id=new_assignment_id,
                        chapter_id=new_chapter_id,
                        max_score=assignment.max_score,
                        due_date=None,
                    )
                )

            for block in sorted(blocks_by_chapter.get(chapter.id, []), key=lambda b: b.order_index):
                new_block_id = uuid.uuid4()
                block_id_map[str(block.id)] = str(new_block_id)
                db.add(
                    ChapterBlock(
                        id=new_block_id,
                        chapter_id=new_chapter_id,
                        block_type=block.block_type,
                        order_index=block.order_index,
                        quiz_id=quiz_id_map.get(str(block.quiz_id)) if block.quiz_id else None,
                        assignment_id=assignment_id_map.get(str(block.assignment_id)) if block.assignment_id else None,
                        file_bucket=block.file_bucket,
                        file_path=block.file_path,
                        file_name=block.file_name,
                    )
                )

    # Phase 5z: fan a single bulk SELECT + INSERT per entity_type across
    # the whole clone tree so the new course inherits its bilingual
    # text from the original instead of landing as an empty draft.
    db.flush()
    _clone_cv_rows(db, entity_type="course", id_map=course_id_map, fields=_CLONABLE_TEXT_FIELDS["course"])
    _clone_cv_rows(db, entity_type="module", id_map=module_id_map, fields=_CLONABLE_TEXT_FIELDS["module"])
    _clone_cv_rows(db, entity_type="chapter", id_map=chapter_id_map, fields=_CLONABLE_TEXT_FIELDS["chapter"])
    _clone_cv_rows(db, entity_type="chapter_block", id_map=block_id_map, fields=_CLONABLE_TEXT_FIELDS["chapter_block"])
    _clone_cv_rows(db, entity_type="quiz", id_map=quiz_id_map_cv, fields=_CLONABLE_TEXT_FIELDS["quiz"])
    _clone_cv_rows(
        db, entity_type="quiz_question", id_map=question_id_map_cv, fields=_CLONABLE_TEXT_FIELDS["quiz_question"]
    )
    _clone_cv_rows(db, entity_type="quiz_option", id_map=option_id_map_cv, fields=_CLONABLE_TEXT_FIELDS["quiz_option"])
    _clone_cv_rows(
        db, entity_type="assignment", id_map=assignment_id_map_cv, fields=_CLONABLE_TEXT_FIELDS["assignment"]
    )

    # Append " (Copy)" to the course title so the catalog stays
    # distinguishable. Try the source-locale row first; fall back to
    # any active title row on the clone if the source locale row
    # didn't exist (draft courses that never went through the
    # publish-time MT pass may only have one locale present).
    db.flush()
    candidate = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id == new_course_id,
            ContentVersion.field == "title",
            ContentVersion.locale == original.source_locale,
            ContentVersion.superseded_by.is_(None),
        )
        .one_or_none()
        or db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id == new_course_id,
            ContentVersion.field == "title",
            ContentVersion.superseded_by.is_(None),
        )
        .order_by(ContentVersion.created_at)
        .first()
    )
    if candidate is not None:
        candidate.text = f"{candidate.text} (Copy)"

    db.commit()

    cloned = db.query(Course).options(*_COURSE_TREE).filter(Course.id == new_course_id).first()
    if cloned is not None:
        # Phase 5g/5z: ``courses.title|description`` and
        # ``modules.title|description`` live in cv. Hydrate runtime
        # attrs so the response serializer sees a real title instead
        # of failing the Pydantic ``title`` field check.
        from app.services.translation.resolve_for_display import populate_spine_texts

        populate_spine_texts(db, [cloned])
    return cloned
