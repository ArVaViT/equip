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
