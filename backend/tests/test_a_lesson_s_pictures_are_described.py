"""The publish checklist asks for a description on every picture in a lesson.

A student who cannot see an image hears its description or nothing at all,
and a teacher who is not a web specialist does not know the rule. The check
is ``recommended``, appears only for lessons that have pictures, and reads
the language the teacher writes in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.course import Chapter, Module
from app.services.course_readiness import compute_readiness
from tests._cv_helpers import make_chapter_block_with_content, make_course_with_text
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


def _lesson(db: Session, course_id: str, name: str, html: str, *, locale: str = "en") -> str:
    chapter = Chapter(
        id=f"{name}-{course_id}", course_id=course_id, module_id=f"m-{course_id}", title=name, order_index=0
    )
    db.add(chapter)
    db.flush()
    make_chapter_block_with_content(db, chapter_id=chapter.id, content=html, locale=locale)
    return chapter.id


def test_pictures_without_a_description_are_flagged(db: Session, teacher: User) -> None:
    course = make_course_with_text(db, title="Acts", status="draft", created_by=TEACHER_ID, source_locale="en")
    db.add(Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0))
    db.flush()
    bare = _lesson(db, course.id, "bare", '<p>Map:</p><img src="https://x/map.png">')
    blank = _lesson(db, course.id, "blank", '<img src="https://x/a.png" alt=" ">')
    described = _lesson(db, course.id, "described", '<img src="https://x/a.png" alt="Map of the first journey">')
    text_only = _lesson(db, course.id, "text", "<p>Only words.</p>")
    db.commit()

    checks = {c.id: c for c in compute_readiness(db, course).checks if c.id.startswith("images_have_alt:")}
    assert checks[f"images_have_alt:{bare}"].passed is False
    assert checks[f"images_have_alt:{blank}"].passed is False
    assert checks[f"images_have_alt:{described}"].passed is True
    assert f"images_have_alt:{text_only}" not in checks
    assert {c.severity for c in checks.values()} == {"recommended"}


def test_headings_out_of_order_are_flagged_across_the_lesson(db: Session, teacher: User) -> None:
    course = make_course_with_text(db, title="Acts", status="draft", created_by=TEACHER_ID, source_locale="en")
    db.add(Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0))
    db.flush()
    jump = _lesson(db, course.id, "jump", "<h2>Part</h2><h4>Detail</h4>")
    page_title = _lesson(db, course.id, "h1", "<h1>Again the title</h1>")
    # Two blocks: h2 in the first, h3 opening the second — nothing skipped.
    tidy = Chapter(id=f"tidy-{course.id}", course_id=course.id, module_id=f"m-{course.id}", title="t", order_index=0)
    db.add(tidy)
    db.flush()
    make_chapter_block_with_content(db, chapter_id=tidy.id, content="<h2>Part</h2><p>x</p>", order_index=0)
    make_chapter_block_with_content(db, chapter_id=tidy.id, content="<h3>Sub</h3><p>y</p>", order_index=1)
    db.commit()

    flagged = {c.id for c in compute_readiness(db, course).checks if c.id.startswith("headings_in_order:")}
    assert flagged == {f"headings_in_order:{jump}", f"headings_in_order:{page_title}"}


def test_a_published_course_is_judged_by_the_edit_still_waiting_for_translations(db: Session, teacher: User) -> None:
    """On a published course an edit waits for every language before readers
    get it. The checklist is the author's, so it reads that edit: a picture
    added today must not pass until the translations land."""
    from app.models.chapter_block import ChapterBlock
    from app.models.staged_content_version import StagedContentVersion

    course = make_course_with_text(db, title="Acts", status="published", created_by=TEACHER_ID, source_locale="en")
    db.add(Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0))
    db.flush()
    lesson = _lesson(db, course.id, "live", '<img src="https://x/a.png" alt="Map">')
    block = db.query(ChapterBlock).filter(ChapterBlock.chapter_id == lesson).one()
    db.add(
        StagedContentVersion(
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale="en",
            course_id=course.id,
            text='<h1>Again the title</h1><img src="https://x/b.png">',
            origin="human",
            source_locale="en",
        )
    )
    db.commit()

    checks = {c.id: c for c in compute_readiness(db, course).checks}
    assert checks[f"images_have_alt:{lesson}"].passed is False
    assert f"headings_in_order:{lesson}" in checks


def test_a_lesson_whose_only_text_is_waiting_counts_as_written(db: Session, teacher: User) -> None:
    """A lesson added to a published course has its text only in staging;
    the author's checklist does not call it empty."""
    from app.models.chapter_block import ChapterBlock
    from app.models.staged_content_version import StagedContentVersion

    course = make_course_with_text(db, title="Acts", status="published", created_by=TEACHER_ID, source_locale="en")
    db.add(Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0))
    db.flush()
    chapter = Chapter(
        id=f"new-{course.id}", course_id=course.id, module_id=f"m-{course.id}", title="new", order_index=0
    )
    db.add(chapter)
    db.flush()
    block = ChapterBlock(chapter_id=chapter.id, block_type="text", order_index=0)
    db.add(block)
    db.flush()
    db.add(
        StagedContentVersion(
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale="en",
            course_id=course.id,
            text="<p>Written today.</p>",
            origin="human",
            source_locale="en",
        )
    )
    db.commit()

    checks = {c.id: c for c in compute_readiness(db, course).checks}
    assert checks[f"reading_has_content:{chapter.id}"].passed is True
