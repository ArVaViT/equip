"""Split the rows that hold two languages at once.

The Daily Challenge generator's fourth round produces an English item
and a Russian rendering of it. In a run of questions from earlier this
year it wrote both into the *English* row, separated by a slash or a
newline, and put the Russian half into the Russian row as well. So an
English reader is offered:

    Clear as crystal / Светлая (прозрачная), как кристалл

as one answer to click. The Russian reader sees the correct Russian
row; nobody looked at the English one. Thirteen rows in production on
2026-08-16, found by re-reading every stored text rather than by any
test.

The repair is deterministic, and this script refuses anything it
cannot prove:

* the row must be filed ``en`` and read as Russian;
* it must split on a separator into a head and a tail;
* the tail must match the Russian row already stored for that same
  entity and field (ignoring case, spacing and final punctuation);
* the head must not itself read as Russian.

Everything else is reported and left alone — including the row whose
English text is simply the Russian verse, which has no English half to
recover and needs re-translating rather than cutting.

Writes through ``record_human_version``, so the old row is superseded
rather than overwritten and the history stays readable.

Use
---
  python -m scripts.repair_bilingual_rows            # dry run, prints the plan
  python -m scripts.repair_bilingual_rows --apply    # do it
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.services.content_versions.write import record_human_version
from app.services.language_detection import carries_language, detect_locale

# The two shapes the generator produced: " / " between the halves, or a
# line break. Both are unambiguous — neither appears inside a single
# answer option in this content.
_SEPARATORS = (" / ", "\n")

_TRAILING_PUNCT = re.compile(r"[\s.,;:!?»«\"']+$")


def _comparable(value: str) -> str:
    return _TRAILING_PUNCT.sub("", " ".join(value.split()).lower())


def _english_half(candidate: str, russian_row: str | None) -> str | None:
    """The English half, or ``None`` when this row cannot be proved.

    Two proofs, and either is enough.

    The first is the strongest: the tail is character-for-character the
    Russian row already stored for this field, so the split is not a
    reading of the text — it is the text saying where it was cut.

    The second exists because the first is stricter than the data. One
    row reads "Clear as crystal / Светлая (прозрачная), как кристалл"
    while its Russian row says "Светлая, как кристалл" — the halves
    disagree by one parenthetical, the exact match fails, and the row
    stayed broken with an English reader looking at both languages. So:
    a head that does not read as Russian, a tail that does, and a
    separator between them is a proof of its own. It says nothing about
    which Russian is right, only that the English half ends where the
    Russian begins, and that is all this is deciding.
    """
    for separator in _SEPARATORS:
        if separator not in candidate:
            continue
        head, _, tail = candidate.partition(separator)
        head, tail = head.strip(), tail.strip()
        if not head or not tail:
            continue
        if carries_language(head) and detect_locale(head) == "ru":
            continue
        if russian_row and _comparable(tail) == _comparable(russian_row):
            return head
        if carries_language(tail) and detect_locale(tail) == "ru":
            return head
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repair instead of printing it")
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    session_factory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    db = session_factory()
    repaired = skipped = 0
    try:
        rows = db.execute(
            text("""
                select entity_type, entity_id, field, text
                from content_versions
                where superseded_by is null and locale = 'en' and status = 'ok' and text is not null
            """)
        ).all()

        for row in rows:
            if not carries_language(row.text) or detect_locale(row.text) != "ru":
                continue
            russian = db.execute(
                text("""
                    select text from content_versions
                    where entity_type = :et and entity_id = :eid and field = :f
                      and locale = 'ru' and superseded_by is null
                """),
                {"et": row.entity_type, "eid": row.entity_id, "f": row.field},
            ).scalar()
            english = _english_half(row.text, russian)
            if english is None:
                skipped += 1
                print(f"SKIP  {row.entity_type}.{row.field} — cannot prove a split: {row.text[:70]}")
                continue

            repaired += 1
            print(f"FIX   {row.entity_type}.{row.field}")
            print(f"      was: {row.text[:90]}")
            print(f"      now: {english[:90]}")
            if args.apply:
                record_human_version(
                    db,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    field=row.field,
                    locale="en",
                    text=english,
                )
                # Whatever was translated from this row was translated
                # from both languages at once — the German for this one
                # carries the Russian half's parenthetical. Clearing the
                # hash asks for those again, and leaves their current
                # text serving until better arrives.
                db.execute(
                    text("""
                        update content_versions set source_hash = null
                        where entity_type = :et and entity_id = :eid and field = :f
                          and origin = 'mt' and superseded_by is null
                    """),
                    {"et": row.entity_type, "eid": row.entity_id, "f": row.field},
                )

        if args.apply:
            db.commit()
    finally:
        db.close()

    print(f"\n{repaired} repairable, {skipped} left alone{' — written' if args.apply else ' (dry run)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
