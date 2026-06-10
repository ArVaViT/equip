"""Smoke test for ``scripts/seed_fat_test_course.py``.

Pins the seed shape end-to-end on the SQLite test DB. The script is
designed to be idempotent — a second invocation with the same args
must not duplicate rows. Both invariants tested here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.chapter_progress import ChapterProgress
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.user import User as UserModel
from scripts.seed_fat_test_course import purge, seed, seed_students

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


class TestSeedFatCourse:
    def test_seed_creates_expected_shape(self, db: Session, teacher: User) -> None:
        report = seed(
            db,
            course_id="fat-shape-1",
            title="Fat Shape Test",
            modules=3,
            chapters_per_module=5,
            teacher=teacher,
        )

        # Report-level invariants.
        assert report["modules"] == 3
        assert report["chapters"] == 15
        # Chapter cycle is reading, quiz, assignment, reading, quiz —
        # so 5 chapters per module → 2 quizzes + 1 assignment + 2
        # reading. With 3 modules: 6 quizzes, 3 assignments.
        assert report["quizzes"] == 6
        assert report["assignments"] == 3

        # DB-level invariants.
        assert db.query(Course).filter(Course.id == "fat-shape-1").count() == 1
        assert db.query(Module).filter(Module.course_id == "fat-shape-1").count() == 3
        chapter_ids = [
            c.id
            for c in db.query(Chapter)
            .join(Module, Chapter.module_id == Module.id)
            .filter(Module.course_id == "fat-shape-1")
            .all()
        ]
        assert len(chapter_ids) == 15
        # One block per chapter.
        assert db.query(ChapterBlock).filter(ChapterBlock.chapter_id.in_(chapter_ids)).count() == 15
        # One question per quiz, 4 options per question.
        assert db.query(Quiz).filter(Quiz.chapter_id.in_(chapter_ids)).count() == 6
        assert db.query(QuizQuestion).count() == 6
        assert db.query(QuizOption).count() == 24
        # Each assignment shows up once.
        assert db.query(Assignment).filter(Assignment.chapter_id.in_(chapter_ids)).count() == 3

    def test_seed_is_idempotent(self, db: Session, teacher: User) -> None:
        """A second invocation with the same course_id must not
        duplicate rows. Operators are expected to re-run after editing
        the script."""
        seed(
            db,
            course_id="fat-idem",
            title="Fat Idempotent",
            modules=2,
            chapters_per_module=5,
            teacher=teacher,
        )
        # Capture row counts after the first run.
        course_count_1 = db.query(Course).filter(Course.id == "fat-idem").count()
        module_count_1 = db.query(Module).filter(Module.course_id == "fat-idem").count()
        chapter_count_1 = (
            db.query(Chapter)
            .join(Module, Chapter.module_id == Module.id)
            .filter(Module.course_id == "fat-idem")
            .count()
        )
        quiz_count_1 = (
            db.query(Quiz)
            .join(Chapter, Quiz.chapter_id == Chapter.id)
            .join(Module, Chapter.module_id == Module.id)
            .filter(Module.course_id == "fat-idem")
            .count()
        )

        # Second invocation with the same args.
        seed(
            db,
            course_id="fat-idem",
            title="Fat Idempotent",
            modules=2,
            chapters_per_module=5,
            teacher=teacher,
        )

        # Row counts unchanged.
        assert db.query(Course).filter(Course.id == "fat-idem").count() == course_count_1
        assert db.query(Module).filter(Module.course_id == "fat-idem").count() == module_count_1
        assert (
            db.query(Chapter)
            .join(Module, Chapter.module_id == Module.id)
            .filter(Module.course_id == "fat-idem")
            .count()
            == chapter_count_1
        )
        assert (
            db.query(Quiz)
            .join(Chapter, Quiz.chapter_id == Chapter.id)
            .join(Module, Chapter.module_id == Module.id)
            .filter(Module.course_id == "fat-idem")
            .count()
            == quiz_count_1
        )

    def test_course_lands_as_draft_not_published(self, db: Session, teacher: User) -> None:
        """The script always provisions ``status='draft'`` — operators
        promote to published manually after eyeballing the catalog
        render. A stray prod run must not surface to students."""
        seed(
            db,
            course_id="fat-draft",
            title="Fat Draft Status",
            modules=1,
            chapters_per_module=1,
            teacher=teacher,
        )
        course = db.query(Course).filter(Course.id == "fat-draft").first()
        assert course is not None
        assert course.status == "draft"


class TestSeedStudents:
    def test_students_enrolled_with_consistent_progress(self, db: Session, teacher: User) -> None:
        seed(db, course_id="fat-st", title="Fat Students", modules=2, chapters_per_module=5, teacher=teacher)
        report = seed_students(db, course_id="fat-st", students=10)
        assert report["students"] == 10

        enrollments = db.query(Enrollment).filter(Enrollment.course_id == "fat-st").all()
        assert len(enrollments) == 10
        # Every enrolled user is a synthetic seed student.
        for e in enrollments:
            student = db.query(UserModel).filter(UserModel.id == e.user_id).one()
            assert student.email.endswith("@seed.invalid")

        # enrollment.progress must match the count of completed chapters
        # (10 chapters total → progress == completed * 10).
        total_chapters = (
            db.query(Chapter).join(Module, Chapter.module_id == Module.id).filter(Module.course_id == "fat-st").count()
        )
        assert total_chapters == 10
        for e in enrollments:
            done = (
                db.query(ChapterProgress)
                .join(Chapter, ChapterProgress.chapter_id == Chapter.id)
                .join(Module, Chapter.module_id == Module.id)
                .filter(ChapterProgress.user_id == e.user_id, Module.course_id == "fat-st")
                .count()
            )
            assert e.progress == round(done / total_chapters * 100)

        # The spread is non-trivial: not everyone is at 0 or all at 100.
        progresses = {e.progress for e in enrollments}
        assert len(progresses) > 1

    def test_students_idempotent(self, db: Session, teacher: User) -> None:
        seed(db, course_id="fat-stid", title="Fat Students Idem", modules=2, chapters_per_module=5, teacher=teacher)
        seed_students(db, course_id="fat-stid", students=8)
        enroll_1 = db.query(Enrollment).filter(Enrollment.course_id == "fat-stid").count()
        prog_1 = db.query(ChapterProgress).count()

        seed_students(db, course_id="fat-stid", students=8)
        assert db.query(Enrollment).filter(Enrollment.course_id == "fat-stid").count() == enroll_1
        assert db.query(ChapterProgress).count() == prog_1

    def test_seed_with_students_arg(self, db: Session, teacher: User) -> None:
        report = seed(
            db, course_id="fat-inline", title="Inline", modules=1, chapters_per_module=5, teacher=teacher, students=5
        )
        assert report["students"] == 5
        assert db.query(Enrollment).filter(Enrollment.course_id == "fat-inline").count() == 5


class TestPurge:
    def test_purge_removes_everything_seeded(self, db: Session, teacher: User) -> None:
        seed(
            db, course_id="fat-purge", title="Fat Purge", modules=3, chapters_per_module=5, teacher=teacher, students=6
        )
        # Sanity: rows exist before purge.
        assert db.query(Course).filter(Course.id == "fat-purge").count() == 1
        assert db.query(Enrollment).filter(Enrollment.course_id == "fat-purge").count() == 6
        cv_before = db.query(ContentVersion).count()
        assert cv_before > 0

        report = purge(db, course_id="fat-purge")
        assert report["students"] == 6
        assert report["modules"] == 3

        # Nothing for this course survives.
        assert db.query(Course).filter(Course.id == "fat-purge").count() == 0
        assert db.query(Module).filter(Module.course_id == "fat-purge").count() == 0
        assert db.query(Enrollment).filter(Enrollment.course_id == "fat-purge").count() == 0
        assert db.query(UserModel).filter(UserModel.email.like("fat-student-fat-purge-%@seed.invalid")).count() == 0
        # content_versions for the seeded entities are gone too.
        assert db.query(ContentVersion).filter(ContentVersion.entity_id == "fat-purge").count() == 0
        # The real teacher is untouched.
        assert db.query(UserModel).filter(UserModel.id == teacher.id).count() == 1

    def test_purge_is_safe_on_unknown_course(self, db: Session, teacher: User) -> None:
        # Purging a course_id that was never seeded is a no-op, not an error.
        report = purge(db, course_id="never-seeded")
        assert report == {"course_id": "never-seeded", "modules": 0, "chapters": 0, "students": 0}
