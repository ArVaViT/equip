"""Every live row that names a book of the Bible in a spelling its language does not print.

``validation._check_book_names`` runs on a translation as it is made.
This runs the same function over the rows that were already written, and
it is how the number in that check's docstring is obtained and re-obtained
after a repair.

Scope: rows a reader can actually reach — published, undeleted courses
(module and chapter both undeleted) and published Daily Challenge
questions. Roughly 3,300 further translated rows sit in soft-deleted
chapters and nobody is examined on them.

Use
---
  python -m scripts.audit_book_names
  python -m scripts.audit_book_names --locale uk --full

Needs ``DATABASE_URL``. Read-only: one query, one connection, no writes.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

from sqlalchemy import create_engine, text

from app.services.translation.book_names import foreign_book_names

_SQL = text("""
WITH live_course AS (
    SELECT id::text AS id FROM courses
    WHERE deleted_at IS NULL AND status = 'published'
),
live_module AS (
    SELECT m.id::text AS id FROM modules m
    JOIN live_course c ON c.id = m.course_id::text
    WHERE m.deleted_at IS NULL
),
live_chapter AS (
    SELECT ch.id::text AS id FROM chapters ch
    JOIN live_module m ON m.id = ch.module_id::text
    WHERE ch.deleted_at IS NULL
),
live_quiz AS (
    SELECT q.id::text AS id FROM quizzes q JOIN live_chapter ch ON ch.id = q.chapter_id::text
),
live_question AS (
    SELECT qq.id::text AS id FROM quiz_questions qq JOIN live_quiz q ON q.id = qq.quiz_id::text
),
live_dc_question AS (
    SELECT id::text AS id FROM daily_challenge_questions
    WHERE status = 'published' AND rejected = FALSE AND published_at IS NOT NULL
),
reachable AS (
    SELECT 'course' AS entity_type, id FROM live_course
    UNION ALL SELECT 'module', id FROM live_module
    UNION ALL SELECT 'chapter', id FROM live_chapter
    UNION ALL SELECT 'chapter_block', b.id::text FROM chapter_blocks b
        JOIN live_chapter ch ON ch.id = b.chapter_id::text
    UNION ALL SELECT 'quiz', id FROM live_quiz
    UNION ALL SELECT 'quiz_question', id FROM live_question
    UNION ALL SELECT 'quiz_option', o.id::text FROM quiz_options o
        JOIN live_question qq ON qq.id = o.question_id::text
    UNION ALL SELECT 'daily_challenge_question', id FROM live_dc_question
    UNION ALL SELECT 'daily_challenge_option', o.id::text FROM daily_challenge_options o
        JOIN live_dc_question q ON q.id = o.question_id::text
)
SELECT cv.id::text AS version_id, cv.entity_type, cv.entity_id, cv.field, cv.locale,
       ru.text AS source, cv.text AS translation
FROM content_versions cv
JOIN reachable r ON r.entity_type = cv.entity_type AND r.id = cv.entity_id
JOIN content_versions ru
  ON ru.entity_type = cv.entity_type AND ru.entity_id = cv.entity_id
 AND ru.field = cv.field AND ru.locale = 'ru' AND ru.superseded_by IS NULL
WHERE cv.superseded_by IS NULL
  AND cv.origin = 'mt' AND cv.status = 'ok' AND cv.locale <> 'ru'
  AND cv.text IS NOT NULL AND cv.text <> ''
""")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", action="append", help="only this target language (repeatable)")
    parser.add_argument("--full", action="store_true", help="print both texts in full, not just the flags")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    url = url.replace("postgresql+psycopg://", "postgresql://")

    wanted = set(args.locale or ())
    read = 0
    flagged = 0
    counted: Counter[tuple[str, str]] = Counter()

    engine = create_engine(url)
    with engine.connect() as conn:
        for row in conn.execution_options(stream_results=True).execute(_SQL):
            if wanted and row.locale not in wanted:
                continue
            read += 1
            found = foreign_book_names(
                row.source,
                row.translation,
                source_locale="ru",
                target_locale=row.locale,
            )
            if not found:
                continue
            flagged += 1
            for printed, _ in found:
                counted[row.locale, printed] += 1
            named = ", ".join(f"{printed} → {expected}" for printed, expected in found)
            print(f"[{row.locale}] {row.entity_type}/{row.field} {row.entity_id}  version {row.version_id}")
            print(f"    {named}")
            if args.full:
                print(f"    RU: {' '.join((row.source or '').split())}")
                print(f"    TR: {' '.join((row.translation or '').split())}")
    engine.dispose()

    print(f"\n{flagged} of {read} live rows name a book their language does not print")
    for (locale, printed), rows in counted.most_common():
        print(f"    [{locale}] {printed}  x{rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
