"""Seed a "fat" test course for pre-pilot regression testing.

Pilot schools plan to deploy 5+ courses with 30+ modules each; the
two real courses on prod (Деяния + Библия как историч. док) are
nowhere near that shape, so the catalog / dashboard / progress
surfaces have never been stress-tested at realistic pilot scale.

This script provisions one big course (default 35 modules, 5
chapters per module, 175 total chapters) with mixed chapter types
(reading + quiz + assignment), one block per chapter, and one quiz
per quiz-typed chapter. Designed to be idempotent: re-runs with the
same ``--course-id`` upsert the structure rather than duplicating
it.

Run against any environment (SQLite test, Postgres dev, Supabase
staging — never prod). The course is marked ``draft`` so a stray
run against prod doesn't surface to users; promote to ``published``
manually after eyeballing the dashboard render.

Pass ``--students N`` to also enrol N synthetic learners (``@seed.invalid``
addresses) with a deterministic spread of completion — chapter_progress
rows are written so the dashboard / analytics surfaces see internally
consistent partial progress, not just a bare number.

Usage:

    # Structure + 50 students with mixed progress:
    python -m scripts.seed_fat_test_course --course-id fat-test \\
        --teacher-email teacher@example.com \\
        --modules 35 --chapters-per-module 5 --students 50

    # Tear it all back down (structure + students + progress):
    python -m scripts.seed_fat_test_course --course-id fat-test --purge

The teacher must already exist in the ``profiles`` table; we look up
by email and abort if missing rather than auto-create (auto-creating
admin users from a script would be too easy to fat-finger). Synthetic
students, by contrast, are created/removed by the script — they live
only in the seed namespace and ``--purge`` cleans them up.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.chapter_progress import ChapterProgress
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.user import User, UserRole
from app.services.content_versions.write import record_human_version

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_fat_test_course")


# Cycle types deterministically so the seed is reproducible — every
# 5th chapter is reading / quiz / assignment / reading / quiz, etc.
_CHAPTER_TYPE_CYCLE = ("reading", "quiz", "assignment", "reading", "quiz")

# Fixed namespace so synthetic student ids are stable across re-runs
# (idempotency) and trivially identifiable for ``--purge``.
_STUDENT_NS = uuid.UUID("f0f0f0f0-0000-4000-8000-000000000001")


def _student_email(course_id: str, index: int) -> str:
    # ``.invalid`` is a reserved TLD (RFC 2606) — these addresses can
    # never receive real mail, so a stray prod seed can't email anyone.
    return f"fat-student-{course_id}-{index:03d}@seed.invalid"


def _student_id(course_id: str, index: int) -> uuid.UUID:
    return uuid.uuid5(_STUDENT_NS, f"{course_id}:{index}")


def _cv_text(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    text: str,
    locale: str = "en",
    actor_id: uuid.UUID,
) -> None:
    if text:
        record_human_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=locale,
            text=text,
            authored_by=actor_id,
        )


def _ensure_course(db: Session, *, course_id: str, title: str, teacher: User) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        course = Course(
            id=course_id,
            status="draft",  # NEVER auto-publish from a script
            source_locale="en",
            created_by=teacher.id,
            access_mode="public",
            quiz_weight=40,
            assignment_weight=40,
            participation_weight=20,
        )
        db.add(course)
        db.flush()
        _cv_text(
            db,
            entity_type="course",
            entity_id=course.id,
            field="title",
            text=title,
            actor_id=teacher.id,
        )
        _cv_text(
            db,
            entity_type="course",
            entity_id=course.id,
            field="description",
            text="Synthetic course for pilot-scale regression testing. NOT for student use.",
            actor_id=teacher.id,
        )
        logger.info("Created course %s", course_id)
    else:
        logger.info("Course %s exists; reusing", course_id)
    return course


def _ensure_module(
    db: Session,
    *,
    course_id: str,
    index: int,
    teacher: User,
) -> Module:
    module_id = f"{course_id}-mod-{index:03d}"
    module = db.query(Module).filter(Module.id == module_id).first()
    if module is None:
        module = Module(id=module_id, course_id=course_id, order_index=index)
        db.add(module)
        db.flush()
        _cv_text(
            db,
            entity_type="module",
            entity_id=module.id,
            field="title",
            text=f"Module {index + 1}",
            actor_id=teacher.id,
        )
        _cv_text(
            db,
            entity_type="module",
            entity_id=module.id,
            field="description",
            text=f"Auto-seeded module {index + 1} for fat-course testing.",
            actor_id=teacher.id,
        )
    return module


def _ensure_chapter(
    db: Session,
    *,
    module: Module,
    index: int,
    chapter_type: str,
) -> Chapter:
    chapter_id = f"{module.id}-ch-{index:03d}"
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if chapter is None:
        chapter = Chapter(
            id=chapter_id,
            module_id=module.id,
            title=f"Chapter {index + 1}",
            order_index=index,
            chapter_type=chapter_type,
        )
        db.add(chapter)
        db.flush()
    return chapter


def _ensure_block(db: Session, *, chapter_id: str, teacher: User) -> None:
    """One text block per chapter so the BlockRenderer + DOMPurify
    pipeline gets exercised at this scale."""
    block_marker = db.query(ChapterBlock).filter(ChapterBlock.chapter_id == chapter_id).first()
    if block_marker is not None:
        return
    block = ChapterBlock(
        id=uuid.uuid4(),
        chapter_id=chapter_id,
        block_type="text",
        order_index=0,
    )
    db.add(block)
    db.flush()
    _cv_text(
        db,
        entity_type="chapter_block",
        entity_id=str(block.id),
        field="content",
        text=(
            "<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Pinned for fat-course regression coverage.</p>"
        ),
        actor_id=teacher.id,
    )


def _ensure_quiz(db: Session, *, chapter_id: str, teacher: User) -> None:
    """One 4-option multiple-choice question per quiz-typed chapter
    so the quiz-attempt flow at scale also gets exercised."""
    existing = db.query(Quiz).filter(Quiz.chapter_id == chapter_id).first()
    if existing is not None:
        return
    quiz = Quiz(
        id=uuid.uuid4(),
        chapter_id=chapter_id,
        quiz_type="quiz",
        passing_score=70,
    )
    db.add(quiz)
    db.flush()
    _cv_text(
        db,
        entity_type="quiz",
        entity_id=str(quiz.id),
        field="title",
        text="Sample Quiz",
        actor_id=teacher.id,
    )

    question = QuizQuestion(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        question_type="multiple_choice",
        order_index=0,
        points=1,
    )
    db.add(question)
    db.flush()
    _cv_text(
        db,
        entity_type="quiz_question",
        entity_id=str(question.id),
        field="question_text",
        text="2 + 2 = ?",
        actor_id=teacher.id,
    )

    correct_index = 1  # "4"
    for idx, label in enumerate(("3", "4", "5", "6")):
        opt = QuizOption(
            id=uuid.uuid4(),
            question_id=question.id,
            is_correct=(idx == correct_index),
            order_index=idx,
        )
        db.add(opt)
        db.flush()
        _cv_text(
            db,
            entity_type="quiz_option",
            entity_id=str(opt.id),
            field="option_text",
            text=label,
            actor_id=teacher.id,
        )


def _ensure_assignment(db: Session, *, chapter_id: str, teacher: User) -> None:
    existing = db.query(Assignment).filter(Assignment.chapter_id == chapter_id).first()
    if existing is not None:
        return
    assignment = Assignment(
        id=uuid.uuid4(),
        chapter_id=chapter_id,
        max_score=100,
    )
    db.add(assignment)
    db.flush()
    _cv_text(
        db,
        entity_type="assignment",
        entity_id=str(assignment.id),
        field="title",
        text="Sample Assignment",
        actor_id=teacher.id,
    )
    _cv_text(
        db,
        entity_type="assignment",
        entity_id=str(assignment.id),
        field="description",
        text="Write a one-paragraph reflection.",
        actor_id=teacher.id,
    )


def _ordered_chapter_ids(db: Session, *, course_id: str) -> list[str]:
    """Chapter ids for the course in catalog order (module, then chapter
    order_index) — the order a real student would progress through."""
    rows = (
        db.query(Chapter.id)
        .join(Module, Chapter.module_id == Module.id)
        .filter(Module.course_id == course_id)
        .order_by(Module.order_index, Chapter.order_index)
        .all()
    )
    return [r[0] for r in rows]


def _ensure_auth_user(db: Session, *, user_id: uuid.UUID, email: str) -> None:
    """``profiles.id`` FKs to ``auth.users(id)`` — on real Postgres a profile
    row can't exist without its auth row, so seed that first. SQLite test DBs
    have no ``auth`` schema, so skip there (the FK isn't materialised). These
    are ``@seed.invalid`` identities with no password — a staging/dev tool,
    never for prod auth. ``ON CONFLICT DO NOTHING`` keeps it idempotent.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    db.execute(
        text("INSERT INTO auth.users (id, email) VALUES (:id, :email) ON CONFLICT (id) DO NOTHING"),
        {"id": str(user_id), "email": email},
    )
    db.flush()


def _ensure_student(db: Session, *, course_id: str, index: int) -> User:
    student_id = _student_id(course_id, index)
    student = db.query(User).filter(User.id == student_id).first()
    if student is None:
        email = _student_email(course_id, index)
        _ensure_auth_user(db, user_id=student_id, email=email)
        # On a real Supabase database the ``on_auth_user_created`` trigger
        # creates the profile row from the auth insert above — re-check
        # before adding, or the flush would violate ``profiles_pkey``.
        # (SQLite test DBs have neither the auth schema nor the trigger.)
        student = db.query(User).filter(User.id == student_id).first()
    if student is None:
        student = User(
            id=student_id,
            email=_student_email(course_id, index),
            full_name=f"Seed Student {index + 1}",
            role=UserRole.STUDENT.value,
        )
        db.add(student)
        db.flush()
    else:
        student.full_name = f"Seed Student {index + 1}"
        student.role = UserRole.STUDENT.value
    return student


def seed_students(
    db: Session,
    *,
    course_id: str,
    students: int,
) -> dict:
    """Enroll ``students`` synthetic learners in the course with a spread
    of completion. Each student's ``enrollment.progress`` is derived from
    the chapters they've completed, so the dashboard / analytics surfaces
    see internally-consistent partial progress (not just a bare number).

    Idempotent: students, enrollments, and chapter_progress rows all key
    on deterministic ids, so a re-run upserts rather than duplicates.
    """
    chapter_ids = _ordered_chapter_ids(db, course_id=course_id)
    total_chapters = len(chapter_ids)

    enrolled = 0
    for i in range(students):
        student = _ensure_student(db, course_id=course_id, index=i)

        # Deterministic spread of completion across 0..100% so the cohort
        # exercises empty, partial, and finished states simultaneously.
        frac = ((i * 37) % 101) / 100.0
        done = round(frac * total_chapters)
        progress = round(done / total_chapters * 100) if total_chapters else 0

        enrollment_id = f"{course_id}-enroll-{i:03d}"
        enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
        if enrollment is None:
            enrollment = Enrollment(
                id=enrollment_id,
                user_id=student.id,
                course_id=course_id,
                progress=progress,
            )
            db.add(enrollment)
        else:
            enrollment.progress = progress
        db.flush()
        enrolled += 1

        # Mark the first ``done`` chapters complete for this student. Fetch
        # the student's already-recorded chapters in ONE query, then bulk-add
        # the missing ones — the previous per-chapter existence check was
        # O(students * chapters) round-trips (minutes of latency at pilot
        # scale against a remote DB).
        target = chapter_ids[:done]
        if target:
            existing = {
                cid
                for (cid,) in db.query(ChapterProgress.chapter_id).filter(
                    ChapterProgress.user_id == student.id,
                    ChapterProgress.chapter_id.in_(target),
                )
            }
            db.add_all(
                [
                    ChapterProgress(
                        id=uuid.uuid4(),
                        user_id=student.id,
                        chapter_id=chapter_id,
                        completed=True,
                        completed_at=datetime.now(UTC),
                        completion_type="self",
                    )
                    for chapter_id in target
                    if chapter_id not in existing
                ]
            )
        if (i + 1) % 20 == 0:
            db.commit()
            logger.info("Committed through student %s", i + 1)
    db.commit()

    return {"students": enrolled, "chapters_per_student_max": total_chapters}


def seed(
    db: Session,
    *,
    course_id: str,
    title: str,
    modules: int,
    chapters_per_module: int,
    teacher: User,
    students: int = 0,
) -> dict:
    course = _ensure_course(db, course_id=course_id, title=title, teacher=teacher)

    chapter_total = 0
    quiz_total = 0
    assignment_total = 0
    for m_idx in range(modules):
        module = _ensure_module(db, course_id=course.id, index=m_idx, teacher=teacher)
        for c_idx in range(chapters_per_module):
            chapter_type = _CHAPTER_TYPE_CYCLE[c_idx % len(_CHAPTER_TYPE_CYCLE)]
            chapter = _ensure_chapter(db, module=module, index=c_idx, chapter_type=chapter_type)
            chapter_total += 1
            _ensure_block(db, chapter_id=chapter.id, teacher=teacher)
            if chapter_type == "quiz":
                _ensure_quiz(db, chapter_id=chapter.id, teacher=teacher)
                quiz_total += 1
            elif chapter_type == "assignment":
                _ensure_assignment(db, chapter_id=chapter.id, teacher=teacher)
                assignment_total += 1
        if (m_idx + 1) % 5 == 0:
            db.commit()
            logger.info("Committed through module %s", m_idx + 1)
    db.commit()

    report = {
        "course_id": course.id,
        "modules": modules,
        "chapters": chapter_total,
        "quizzes": quiz_total,
        "assignments": assignment_total,
        "students": 0,
    }
    if students > 0:
        student_report = seed_students(db, course_id=course.id, students=students)
        report["students"] = student_report["students"]
    return report


def purge(db: Session, *, course_id: str) -> dict:
    """Tear down everything ``seed`` created for ``course_id``: structure,
    enrollments, progress, synthetic students, and their content_versions.

    Scoped strictly to the deterministic seed namespace — module/chapter/
    enrollment ids carry the ``{course_id}-`` prefix and students match the
    ``@seed.invalid`` pattern — so it can't touch real data even if pointed
    at the wrong DB. Deletes in FK-safe order.
    """
    chapter_ids = _ordered_chapter_ids(db, course_id=course_id)
    module_ids = [r[0] for r in db.query(Module.id).filter(Module.course_id == course_id).all()]
    quiz_ids = [r[0] for r in db.query(Quiz.id).filter(Quiz.chapter_id.in_(chapter_ids)).all()] if chapter_ids else []
    question_ids = (
        [r[0] for r in db.query(QuizQuestion.id).filter(QuizQuestion.quiz_id.in_(quiz_ids)).all()] if quiz_ids else []
    )
    option_ids = (
        [r[0] for r in db.query(QuizOption.id).filter(QuizOption.question_id.in_(question_ids)).all()]
        if question_ids
        else []
    )
    block_ids = (
        [r[0] for r in db.query(ChapterBlock.id).filter(ChapterBlock.chapter_id.in_(chapter_ids)).all()]
        if chapter_ids
        else []
    )
    assignment_ids = (
        [r[0] for r in db.query(Assignment.id).filter(Assignment.chapter_id.in_(chapter_ids)).all()]
        if chapter_ids
        else []
    )
    student_ids = [
        r[0] for r in db.query(User.id).filter(User.email.like(f"fat-student-{course_id}-%@seed.invalid")).all()
    ]

    # Every entity whose text lives in content_versions, as (entity_type, id).
    cv_entities: list[tuple[str, str]] = [("course", course_id)]
    cv_entities += [("module", m) for m in module_ids]
    cv_entities += [("chapter_block", str(b)) for b in block_ids]
    cv_entities += [("quiz", str(q)) for q in quiz_ids]
    cv_entities += [("quiz_question", str(q)) for q in question_ids]
    cv_entities += [("quiz_option", str(o)) for o in option_ids]
    cv_entities += [("assignment", str(a)) for a in assignment_ids]

    # Leaf rows first.
    db.query(ChapterProgress).filter(ChapterProgress.chapter_id.in_(chapter_ids)).delete(synchronize_session=False)
    if student_ids:
        db.query(ChapterProgress).filter(ChapterProgress.user_id.in_(student_ids)).delete(synchronize_session=False)
    db.query(Enrollment).filter(Enrollment.course_id == course_id).delete(synchronize_session=False)
    if option_ids:
        db.query(QuizOption).filter(QuizOption.id.in_(option_ids)).delete(synchronize_session=False)
    if question_ids:
        db.query(QuizQuestion).filter(QuizQuestion.id.in_(question_ids)).delete(synchronize_session=False)
    if quiz_ids:
        db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)
    if assignment_ids:
        db.query(Assignment).filter(Assignment.id.in_(assignment_ids)).delete(synchronize_session=False)
    if block_ids:
        db.query(ChapterBlock).filter(ChapterBlock.id.in_(block_ids)).delete(synchronize_session=False)
    if chapter_ids:
        db.query(Chapter).filter(Chapter.id.in_(chapter_ids)).delete(synchronize_session=False)
    if module_ids:
        db.query(Module).filter(Module.id.in_(module_ids)).delete(synchronize_session=False)
    db.query(Course).filter(Course.id == course_id).delete(synchronize_session=False)

    for entity_type, entity_id in cv_entities:
        db.query(ContentVersion).filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
        ).delete(synchronize_session=False)

    if student_ids:
        db.query(User).filter(User.id.in_(student_ids)).delete(synchronize_session=False)
        # Profiles FK to auth.users — drop the seeded auth rows too so purge
        # leaves nothing behind (postgres only; SQLite has no auth schema).
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(
                text("DELETE FROM auth.users WHERE id = ANY(:ids)"),
                {"ids": [str(sid) for sid in student_ids]},
            )

    db.commit()
    return {
        "course_id": course_id,
        "modules": len(module_ids),
        "chapters": len(chapter_ids),
        "students": len(student_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-id", default="fat-test", help="Course id slug")
    parser.add_argument("--title", default="Fat Test Course", help="Display title")
    parser.add_argument("--modules", type=int, default=35, help="Module count")
    parser.add_argument(
        "--chapters-per-module",
        type=int,
        default=5,
        help="Chapters per module (mixed types: reading / quiz / assignment)",
    )
    parser.add_argument(
        "--students",
        type=int,
        default=0,
        help="Synthetic students to enrol with a spread of progress (0 = course structure only)",
    )
    parser.add_argument(
        "--teacher-email",
        help="Email of the existing User row to set as course owner (required unless --purge)",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Tear down everything previously seeded for --course-id (structure + students + progress)",
    )
    args = parser.parse_args()

    engine = _get_engine()
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    if args.purge:
        with SessionFactory() as db:
            report = purge(db, course_id=args.course_id)
            logger.info(
                "Purged course=%s modules=%d chapters=%d students=%d",
                report["course_id"],
                report["modules"],
                report["chapters"],
                report["students"],
            )
        return 0

    if args.modules < 1 or args.chapters_per_module < 1:
        logger.error("modules and chapters-per-module must be >= 1")
        return 1
    if args.students < 0:
        logger.error("students must be >= 0")
        return 1
    if not args.teacher_email:
        logger.error("--teacher-email is required when seeding (omit only with --purge)")
        return 1

    with SessionFactory() as db:
        teacher = db.query(User).filter(User.email == args.teacher_email).first()
        if teacher is None:
            logger.error(
                "Teacher %s not found in profiles. Create the user via the app first, then re-run.",
                args.teacher_email,
            )
            return 1

        report = seed(
            db,
            course_id=args.course_id,
            title=args.title,
            modules=args.modules,
            chapters_per_module=args.chapters_per_module,
            teacher=teacher,
            students=args.students,
        )
        logger.info(
            "Seeded course=%s modules=%d chapters=%d quizzes=%d assignments=%d students=%d",
            report["course_id"],
            report["modules"],
            report["chapters"],
            report["quizzes"],
            report["assignments"],
            report["students"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
