"""How long a course takes to read — the "about N hours" on the course page.

An adult decides whether to start a course in about ten seconds, and the
honest answer is a number. It is counted from the text the reader will get,
at the lesson page's own reading speeds, and it is visible exactly when the
course page is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.course import Chapter, Module
from app.services.reading_time import count_words, minutes_for
from tests._cv_helpers import make_chapter_block_with_content, make_course_with_text
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _words(n: int) -> str:
    return "<p>" + " ".join(["слово"] * n) + "</p>"


def _course(db: Session, *, status: str = "published", access_mode: str = "public") -> tuple[str, str, str]:
    course = make_course_with_text(
        db,
        title="Деяния",
        status=status,
        source_locale="ru",
        locale="ru",
        created_by=TEACHER_ID,
        access_mode=access_mode,
    )
    module = Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0)
    reading = Chapter(id=f"r-{course.id}", course_id=course.id, module_id=module.id, title="R", order_index=0)
    quiz = Chapter(
        id=f"q-{course.id}", course_id=course.id, module_id=module.id, title="Q", order_index=1, chapter_type="quiz"
    )
    db.add_all([module, reading, quiz])
    db.flush()
    # 320 words in two text blocks: two minutes in Russian (160 a minute).
    make_chapter_block_with_content(db, chapter_id=reading.id, content=_words(200), locale="ru")
    make_chapter_block_with_content(db, chapter_id=reading.id, order_index=1, content=_words(120), locale="ru")
    # A quiz block's text is not reading, and neither is a test lesson's own
    # introduction: the lesson page shows no minutes for it, so neither may the course.
    make_chapter_block_with_content(db, chapter_id=quiz.id, block_type="quiz", content=_words(500), locale="ru")
    make_chapter_block_with_content(db, chapter_id=quiz.id, order_index=1, content=_words(400), locale="ru")
    db.commit()
    return course.id, reading.id, quiz.id


class TestCounting:
    def test_words_are_counted_as_the_lesson_page_counts_them(self) -> None:
        # Tags, entities and a verse number are not words; a hyphenated name is one.
        assert count_words("<p>Ин&nbsp;3:16 <strong>так</strong> возлюбил Иоанна-Крестителя</p>") == 4
        # A Slavonic abbreviation under a titlo is one word, not two.
        assert count_words("\u0411\u0433\u0483\u044a") == 1

    def test_minutes_round_as_the_lesson_page_rounds(self) -> None:
        assert minutes_for(0, "ru") == 0
        assert minutes_for(79, "ru") == 0  # under half a minute
        assert minutes_for(80, "ru") == 1
        assert minutes_for(320, "ru") == 2
        assert minutes_for(440, "en") == 2


class TestTheEndpoint:
    def test_a_visitor_sees_the_minutes_of_a_published_course(self, anon_client: TestClient, db: Session) -> None:
        course_id, reading, quiz = _course(db)
        r = anon_client.get(f"/api/v1/courses/{course_id}/reading-time", headers={"Accept-Language": "ru"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["chapters"] == {reading: 2, quiz: 0}
        assert body["total_minutes"] == 2

    def test_hidden_exactly_where_the_course_page_is(self, anon_client: TestClient, db: Session) -> None:
        for status, access in (("draft", "public"), ("published", "institute")):
            course_id, _, _ = _course(db, status=status, access_mode=access)
            page = anon_client.get(f"/api/v1/courses/{course_id}")
            minutes = anon_client.get(f"/api/v1/courses/{course_id}/reading-time")
            assert page.status_code == minutes.status_code == 404, (status, access)
