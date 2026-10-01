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


def count_words(html: str) -> int:
    """Words in an HTML fragment: tags and entities are not words."""
    return len(_ENTITY.sub(" ", _TAG.sub(" ", html)).split())


def minutes_for(words: int, locale: str) -> int:
    """Whole minutes, never 0 for a lesson that has text."""
    if words <= 0:
        return 0
    return max(1, math.ceil(words / WORDS_PER_MINUTE.get(locale, 200)))


def course_reading_minutes(db: Session, course: Course, display_locale: str) -> dict[str, int]:
    """``{chapter_id: minutes}`` for every live lesson of ``course``; 0 for a lesson with no text."""
    chapters = db.query(Chapter.id).filter(Chapter.course_id == course.id, Chapter.deleted_at.is_(None)).all()
    chapter_ids = [c.id for c in chapters]
    if not chapter_ids:
        return {}
    blocks = (
        db.query(ChapterBlock.id, ChapterBlock.chapter_id)
        .filter(ChapterBlock.chapter_id.in_(chapter_ids), ChapterBlock.block_type == "text")
        .all()
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
