"""Split the rows the generator labelled with both languages at once.

A sibling of ``repair_bilingual_rows``, for a shape that one is not
built to read. Where that script handles two halves separated by a
slash or a newline, this one handles halves the generator labelled::

    [EN] According to Matthew 4:1, who led Jesus into the wilderness?
    [RU] Согласно Матфею 4:1, кто повел Иисуса в пустыню?

Both labelled halves went into the *English* row and into the *Russian*
row, identically. So every reader of either language is shown the
question twice, once in a language they did not ask for, with a tag in
front of it. Then the pipeline did its job faithfully and translated
the whole thing, so the German and Ukrainian rows carry the labels too.

Sixteen rows in production on 2026-08-16: one Daily Challenge question,
its four answer options, in four languages.

The repair is deterministic and this refuses anything it cannot prove:

* the text must carry at least two distinct language labels;
* the row's own locale must be one of them;
* the segment under that label must be non-empty.

Machine-translated rows are not edited. They are asked for again — the
source they came from is what was wrong, and once it is right they
should be re-translated from it rather than surgically corrected. That
is what clearing ``source_hash`` means, and the sweep picks those up.

Use
---
  python -m scripts.repair_tagged_bilingual_rows            # the plan
  python -m scripts.repair_tagged_bilingual_rows --apply    # do it
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

# ``[EN]``, ``[ru]``, ``[Uk]`` — the generator was not consistent about
# case, and the label is always at the start of its own line or the
# start of the text.
_LABEL = re.compile(r"\[(en|ru|de|uk)\]\s*", re.IGNORECASE)


def _halves(body: str) -> dict[str, str]:
    """Each labelled segment, keyed by its language label."""
    matches = list(_LABEL.finditer(body))
    if len({m.group(1).lower() for m in matches}) < 2:
        return {}
    out: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        segment = body[match.end() : end].strip()
        if segment:
            out[match.group(1).lower()] = segment
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repair instead of printing it")
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    session_factory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    db = session_factory()
    repaired = reopened = skipped = 0
    try:
        rows = db.execute(
            text("""
                select id, entity_type, entity_id, field, locale, origin, text
                from content_versions
                where superseded_by is null and text is not null and text like '%[%]%'
            """)
        ).all()

        for row in rows:
            halves = _halves(row.text)
            if not halves:
                continue

            if row.origin != "human":
                # Translated from a source that was itself wrong. Ask for
                # it again rather than editing the translation in place.
                reopened += 1
                print(f"AGAIN {row.entity_type}.{row.field} [{row.locale}] — translated from a labelled source")
                if args.apply:
                    db.execute(
                        text("update content_versions set source_hash = null where id = :id"),
                        {"id": row.id},
                    )
                continue

            mine = halves.get(row.locale)
            if not mine:
                skipped += 1
                print(f"SKIP  {row.entity_type}.{row.field} [{row.locale}] — no {row.locale} half: {row.text[:60]!r}")
                continue

            repaired += 1
            print(f"FIX   {row.entity_type}.{row.field} [{row.locale}]")
            print(f"      was: {row.text[:80]!r}")
            print(f"      now: {mine[:80]!r}")
            if args.apply:
                record_human_version(
                    db,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    field=row.field,
                    locale=row.locale,
                    text=mine,
                )

        if args.apply:
            db.commit()
    finally:
        db.close()

    print(
        f"\n{repaired} split, {reopened} asked for again, {skipped} left alone{' — written' if args.apply else ' (dry run)'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
