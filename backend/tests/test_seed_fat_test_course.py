"""Smoke test for ``scripts/seed_fat_test_course.py``.

Pins the seed shape end-to-end on the SQLite test DB. The script is
designed to be idempotent — a second invocation with the same args
must not duplicate rows. Both invariants tested here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from scripts.seed_fat_test_course import seed

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
