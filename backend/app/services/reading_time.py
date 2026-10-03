"""How long a course takes to read, lesson by lesson, in the reader's language.

An adult deciding whether to start a course decides "can I manage this" in
about ten seconds, and the honest answer is a number: so many lessons, about
so many hours. Counted from the text the reader will actually get — the
text blocks, in their language — at the same reading speeds the lesson page
uses (`frontend/src/lib/readingTime.ts`), so the course page and the lesson
never disagree.

A rounded estimate, not a promise: quizzes, files and assignments add time
nobody can count from text, and they add none here.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import TYPE_CHECKING

from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter
from app.services.content_versions.read import fetch_cv_entity_texts_with_fallback

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course

#: Words a minute, as the lesson page counts them. Cyrillic words run longer.
WORDS_PER_MINUTE: dict[str, int] = {"ru": 160, "uk": 160, "de": 180, "en": 220}
_TAG = re.compile(r"<[^>]+>")
_ENTITY = re.compile(r"&[a-zA-Z#0-9]+;")
#: A word as the lesson page counts one (``wordsIn`` in ``lib/readingTime.ts``):
#: a letter, then letters, combining marks, apostrophes and hyphens. "3:16"
#: is not a word; "Иоанна-Крестителя" is one, and so is a Slavonic word
#: under a titlo (U+0483 to U+0489 are marks, not breaks).
_WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|[\u0300-\u036f\u0483-\u0489'\u2019-])*")


def count_words(html: str) -> int:
    """Words in an HTML fragment, counted exactly as the lesson page counts them."""
    return len(_WORD.findall(_ENTITY.sub(" ", _TAG.sub(" ", html))))


def minutes_for(words: int, locale: str) -> int:
    """Whole minutes rounded to the nearest, as the lesson page rounds (``Math.round``); 0 under half a minute."""
    return math.floor(words / WORDS_PER_MINUTE.get(locale, 200) + 0.5)


def course_reading_minutes(db: Session, course: Course, display_locale: str) -> dict[str, int]:
    """``{chapter_id: minutes}`` for every live lesson of ``course``; 0 for one with under half a minute of text."""
    chapters = (
        db.query(Chapter.id, Chapter.chapter_type)
        .filter(Chapter.course_id == course.id, Chapter.deleted_at.is_(None))
        .all()
    )
    chapter_ids = [c.id for c in chapters]
    if not chapter_ids:
        return {}
    # Only reading lessons count, as on the lesson page, which shows minutes
    # for nothing else: a test's or an assignment's introduction added time to
    # the course that the lesson itself never claimed (review, 2026-10-01).
    # Anything that is not a test, an exam or an assignment is reading — the
    # frontend's normalizeChapterType folds legacy types into it the same way.
    reading = [c.id for c in chapters if c.chapter_type not in ("quiz", "exam", "assignment")]
    blocks = (
        (
            db.query(ChapterBlock.id, ChapterBlock.chapter_id)
            .filter(ChapterBlock.chapter_id.in_(reading), ChapterBlock.block_type == "text")
            .all()
        )
        if reading
        else []
    )
    # Only the text this reader will be served (the default fallback): a
    # lesson still waiting for its translation counts as no minutes rather
    # than borrowing the author's language — and the page shows no time for
    # it rather than a number for a text the reader cannot read yet.
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="chapter_block",
        entity_ids=[str(b.id) for b in blocks],
        fields=["content"],
        display_locale=display_locale,
        source_locale=course.source_locale,
    )
    words: dict[str, int] = defaultdict(int)
    for block in blocks:
        words[block.chapter_id] += count_words(texts.get((str(block.id), "content")) or "")
    return {cid: minutes_for(words[cid], display_locale) for cid in chapter_ids}
