"""The PDF export prints the course, not the module walk.

A chapter belongs to its course; a module is an optional grouping. The
export used to reach every lesson through ``course.modules``, so a
lesson no module grouped was in neither the contents nor the body — and
nothing failed to say so. That is the whole reason these tests read the
text back out of the PDF instead of checking the ``%PDF-`` magic: the
defect this file guards against produces a perfectly valid document
with a piece of the course missing from it.

Three shapes, because a course can be any of them:

* every lesson inside a module — how courses were built before the move;
* no modules at all — a short course written straight into the course;
* mixed — some lessons grouped, some held by the course directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.course import Chapter
from app.services.content_versions.write import record_human_version

from ._cv_helpers import make_course_with_text, make_module_with_text
from ._pdf_text import pdf_lines, printed_order
from .conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


# ── seeding ──────────────────────────────────────────────────────────


def _course(db: Session, course_id: str):
    return make_course_with_text(
        db,
        course_id=course_id,
        title="Course",
        description="A course.",
        status="published",
        source_locale="en",
        created_by=TEACHER_ID,
    )


def _module(db: Session, *, module_id: str, course_id: str, title: str, order_index: int = 0):
    return make_module_with_text(
        db,
        module_id=module_id,
        course_id=course_id,
        title=title,
        order_index=order_index,
    )


def _chapter(
    db: Session,
    *,
    chapter_id: str,
    course_id: str,
    module_id: str | None,
    title: str,
    order_index: int,
    deleted_at=None,
) -> Chapter:
    """A lesson, with the cv row its title is read back from.

    ``chapters.title`` is a real column, but the export hydrates it from
    ``content_versions`` at the reader's locale — a lesson with no row
    there prints as an empty heading, so the row is not optional here.
    """
    chapter = Chapter(
        id=chapter_id,
        module_id=module_id,
        course_id=course_id,
        title=title,
        order_index=order_index,
        chapter_type="reading",
        deleted_at=deleted_at,
    )
    db.add(chapter)
    db.flush()
    record_human_version(
        db,
        entity_type="chapter",
        entity_id=chapter_id,
        field="title",
        locale="en",
        text=title,
    )
    db.commit()
    return chapter


def _export(client: TestClient, course_id: str) -> bytes:
    response = client.get(f"/api/v1/courses/{course_id}/export.pdf", headers={"Accept-Language": "en"})
    assert response.status_code == 200
    assert response.content[:5] == b"%PDF-"
    return response.content


# ── the three shapes ─────────────────────────────────────────────────


class TestTheThreeShapesOfACourse:
    def test_a_course_of_modules_prints_every_lesson_under_its_module(self, client: TestClient, db: Session) -> None:
        """The shape that already worked, pinned so the rewrite keeps it."""
        course = _course(db, "pdf-shape-modules")
        _module(db, module_id="sm-m1", course_id=course.id, title="First Module", order_index=0)
        _module(db, module_id="sm-m2", course_id=course.id, title="Second Module", order_index=1)
        _chapter(db, chapter_id="sm-c1", course_id=course.id, module_id="sm-m1", title="Alpha", order_index=0)
        _chapter(db, chapter_id="sm-c2", course_id=course.id, module_id="sm-m1", title="Beta", order_index=1)
        _chapter(db, chapter_id="sm-c3", course_id=course.id, module_id="sm-m2", title="Gamma", order_index=2)

        pdf = _export(client, course.id)
        titles = ["First Module", "Alpha", "Beta", "Second Module", "Gamma"]
        assert printed_order(pdf, titles) == titles * 2

    def test_a_course_without_modules_prints_a_flat_list_of_lessons(self, client: TestClient, db: Session) -> None:
        """No modules, so no group headings — and no empty ones either.

        The lessons are the document. Before the rewrite this course
        exported as a title page and an empty contents list.
        """
        course = _course(db, "pdf-shape-flat")
        _chapter(db, chapter_id="sf-c1", course_id=course.id, module_id=None, title="Alpha", order_index=0)
        _chapter(db, chapter_id="sf-c2", course_id=course.id, module_id=None, title="Beta", order_index=1)
        _chapter(db, chapter_id="sf-c3", course_id=course.id, module_id=None, title="Gamma", order_index=2)

        pdf = _export(client, course.id)
        lessons = ["Alpha", "Beta", "Gamma"]
        assert printed_order(pdf, lessons) == lessons * 2
        # The document is one flat run: contents, then the lessons. A
        # course with no modules must not sprout a heading over them.
        assert "Untitled" not in pdf_lines(pdf)

    def test_a_mixed_course_puts_each_lesson_where_its_order_index_says(self, client: TestClient, db: Session) -> None:
        """Grouped and loose lessons in one course.

        The order is the course's own ``order_index``: the module takes
        the position of its first lesson and keeps its lessons together,
        and a lesson the course holds directly sits where its own number
        puts it — before the module here, and after it.
        """
        course = _course(db, "pdf-shape-mixed")
        _module(db, module_id="mx-m1", course_id=course.id, title="The Module", order_index=0)
        _chapter(db, chapter_id="mx-c0", course_id=course.id, module_id=None, title="Opening", order_index=0)
        _chapter(db, chapter_id="mx-c1", course_id=course.id, module_id="mx-m1", title="Alpha", order_index=1)
        _chapter(db, chapter_id="mx-c2", course_id=course.id, module_id="mx-m1", title="Beta", order_index=2)
        _chapter(db, chapter_id="mx-c3", course_id=course.id, module_id=None, title="Closing", order_index=3)

        pdf = _export(client, course.id)
        expected = ["Opening", "The Module", "Alpha", "Beta", "Closing"]
        assert printed_order(pdf, expected) == expected * 2


class TestNothingEmptyAndNothingBinned:
    def test_a_module_without_lessons_leaves_no_rubric(self, client: TestClient, db: Session) -> None:
        """A module is a heading over lessons. With none, it is nothing —
        it used to print a heading and a page break over empty space."""
        course = _course(db, "pdf-empty-module")
        _module(db, module_id="em-m1", course_id=course.id, title="Full Module", order_index=0)
        _module(db, module_id="em-m2", course_id=course.id, title="Hollow Module", order_index=1)
        _chapter(db, chapter_id="em-c1", course_id=course.id, module_id="em-m1", title="Alpha", order_index=0)

        lines = pdf_lines(_export(client, course.id))
        assert "Full Module" in lines
        assert "Hollow Module" not in lines

    def test_a_binned_lesson_and_a_binned_module_stay_out(self, client: TestClient, db: Session) -> None:
        """Soft-deleted rows are not in the course any more.

        The binned module's surviving lesson is a live lesson of the
        course, so it still prints — under no heading, which is what
        ``delete_module`` leaves behind when it detaches what it kept.
        """
        from datetime import UTC, datetime

        gone = datetime.now(UTC)
        course = _course(db, "pdf-binned")
        _module(db, module_id="bn-m1", course_id=course.id, title="Live Module", order_index=0)
        binned_module = _module(db, module_id="bn-m2", course_id=course.id, title="Binned Module", order_index=1)
        binned_module.deleted_at = gone
        _chapter(db, chapter_id="bn-c1", course_id=course.id, module_id="bn-m1", title="Alpha", order_index=0)
        _chapter(
            db,
            chapter_id="bn-c2",
            course_id=course.id,
            module_id="bn-m1",
            title="Binned Lesson",
            order_index=1,
            deleted_at=gone,
        )
        _chapter(db, chapter_id="bn-c3", course_id=course.id, module_id="bn-m2", title="Orphan", order_index=2)
        db.commit()

        lines = pdf_lines(_export(client, course.id))
        assert "Alpha" in lines
        assert "Binned Lesson" not in lines
        assert "Binned Module" not in lines
        # Live under a binned module: kept, and printed without a heading.
        assert "Orphan" in lines
