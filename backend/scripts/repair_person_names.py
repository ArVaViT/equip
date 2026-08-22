"""Call each person by the name their language prints for them.

Ten live rows name a person with a spelling the language does not print.
Eight call the first martyr «Степан» — the ordinary Ukrainian given name
Stepan — and every one of those eight is an assessment item, while the
lessons those questions examine print «Стефан». Two call Claudius Lysias
«Лисий» (which reads in Ukrainian as the adjective *bald*) and «Клавдій
Лій» (which is a name in no language), where the same course prints
«Лісій» two paragraphs earlier.

The rule is fixed in ``services/translation/person_names.py``, so no row
written from now on can carry these. This mends the rows written before
it.

The repair is one letter, or two, and it is written out by hand
-----------------------------------------------------------------

Not derived. «Степана» and «Стефана» differ by a letter in the stem, so
a stem substitution would work for that name and would be luck rather
than a rule — «Лій» and «Лісій» are not related that way at all, and a
rule general enough to cover both would be general enough to rewrite
words nobody inspected. Every substitution below is a spelling somebody
read, paired with the spelling that language prints for the same person
in the same grammatical case.

What it refuses
---------------
A row is mended only when all four hold, and is reported and left alone
otherwise:

* **the check must name it first** — the repair is not a search. If
  ``foreign_person_names`` is silent on a row, this script has no
  opinion about it, and that keeps the two in step: whatever the check
  learns to see, this learns to mend, and never the reverse;
* **every spelling it names must be written down here** — a flagged word
  with no substitution is a spelling nobody has read, and guessing at
  it is exactly the thing the table exists to refuse;
* **nothing but those words may move** — the capitalised words of the
  row must come out identical, one for one, except where a listed
  spelling was replaced by its listed repair. A row whose other words
  shift is not this defect;
* **the check must go quiet, and nothing else may start** — the row is
  re-validated whole, and any issue that was not there before the
  repair means the repair caused it.

Usage::

  python -m scripts.repair_person_names            # dry run
  python -m scripts.repair_person_names --apply
  python -m scripts.repair_person_names --apply --include-human
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Final

from sqlalchemy import text as sql
from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.services.translation.person_names import foreign_person_names
from app.services.translation.proper_names import capitalised_words
from app.services.translation.staged_pipeline import _content_kind_of
from app.services.translation.validation import validate_translation

#: Locale → the spelling as it was read on production → the spelling
#: that language prints, in the same case. Hand-written, one line per
#: form somebody actually read.
_REPAIRS: Final[dict[str, dict[str, str]]] = {
    "uk": {
        # Куліш 1905, the edition this platform serves, has «Стефана» at
        # Acts 6:5, 7:59, 8:2, 11:19 and 22:20.
        "Степан": "Стефан",
        "Степана": "Стефана",
        "Степану": "Стефану",
        "Степанові": "Стефанові",
        "Степаном": "Стефаном",
        "Степане": "Стефане",
        # Both forms collapse onto the nominative, which is the case
        # both live rows stand in: «Клавдій Лій — тисячоначальник» and
        # «Лисий вночі відправляє Павла».
        "Лисий": "Лісій",
        "Лій": "Лісій",
    },
}


def _repaired(value: str, table: dict[str, str]) -> str:
    """``value`` with every listed spelling replaced, on word boundaries.

    Longest first, so «Степанові» is never mended as «Степан» plus a
    tail. ``\\b`` is not enough on its own here — it would let a listed
    form match inside a longer Cyrillic word — so the boundary is
    written as "not a word character on either side".
    """
    for bad in sorted(table, key=len, reverse=True):
        value = re.sub(rf"(?<!\w){re.escape(bad)}(?!\w)", table[bad], value)
    return value


def _only_the_listed_words_moved(before: str, after: str, table: dict[str, str], locale: str) -> bool:
    """The capitalised words come out one for one, differing only where a
    listed spelling became its listed repair."""
    was = [word for word, _offset in capitalised_words(before, locale)]
    now = [word for word, _offset in capitalised_words(after, locale)]
    if len(was) != len(now):
        return False
    return all(a == b or table.get(a) == b for a, b in zip(was, now, strict=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repairs")
    parser.add_argument(
        "--include-human",
        action="store_true",
        help="also mend author-written rows, reopening their machine translations",
    )
    args = parser.parse_args()

    session = sessionmaker(bind=_get_engine())()
    rows = session.execute(
        sql(
            """
            SELECT t.id, t.entity_type, t.entity_id, t.field, t.locale, t.origin,
                   t.text AS translation, s.text AS source, s.locale AS source_locale
            FROM content_versions t
            JOIN content_versions s
              ON s.entity_type = t.entity_type AND s.entity_id = t.entity_id
             AND s.field = t.field AND s.superseded_by IS NULL
             AND s.origin = 'human' AND s.locale = 'ru'
            WHERE t.superseded_by IS NULL AND t.status = 'ok'
              AND t.locale = ANY(:locales)
            """
        ),
        {"locales": list(_REPAIRS)},
    ).all()

    planned: list[tuple[str, str, str, str, str]] = []
    human: list[tuple[str, str, str, str, str]] = []
    refused: list[tuple[str, str]] = []

    for row in rows:
        foreign = foreign_person_names(
            row.source,
            row.translation,
            source_locale=row.source_locale,
            target_locale=row.locale,
        )
        if not foreign:
            continue
        label = f"[{row.locale}] {row.entity_type}.{row.field} {row.id}"
        table = _REPAIRS[row.locale]
        unlisted = [printed for printed, _expected in foreign if printed not in table]
        if unlisted:
            refused.append((label, f"no substitution written down for {', '.join(unlisted)}"))
            continue

        mended = _repaired(row.translation, table)
        if mended == row.translation:
            refused.append((label, "the spelling the check named is not where the repair looked"))
            continue
        if not _only_the_listed_words_moved(row.translation, mended, table, row.locale):
            refused.append((label, "more than the listed spellings would move"))
            continue
        still = foreign_person_names(row.source, mended, source_locale=row.source_locale, target_locale=row.locale)
        if still:
            refused.append((label, f"the check still names {still} after the repair"))
            continue

        kind = _content_kind_of(row.entity_type, row.field)
        was = {
            i.code
            for i in validate_translation(
                source=row.source,
                translated=row.translation,
                source_locale=row.source_locale,
                target_locale=row.locale,
                content_kind=kind,
            )
        }
        now = {
            i.code
            for i in validate_translation(
                source=row.source,
                translated=mended,
                source_locale=row.source_locale,
                target_locale=row.locale,
                content_kind=kind,
            )
        }
        caused = now - was
        if caused:
            refused.append((label, f"the repair would cause {', '.join(sorted(caused))}"))
            continue

        named = ", ".join(f"{printed} → {expected}" for printed, expected in foreign)
        target = human if row.origin == "human" else planned
        target.append((str(row.id), label, row.translation, mended, named))

    for label, why in refused:
        print(f"REFUSED  {label}: {why}")
    for verb, batch in (("HUMAN ", human), ("REPAIR", planned)):
        for _id, label, before, after, named in batch:
            print(f"{verb}   {label}: {named}")
            # The live sentence around the first substitution, printed
            # both ways. A repair nobody read is a repair nobody checked.
            at = min((before.find(bad) for bad in _REPAIRS[label[1:3]] if bad in before), default=-1)
            if at >= 0:
                print(f"           …{before[max(0, at - 45) : at + 55]}…")
                print(f"        -> …{after[max(0, at - 45) : at + 57]}…")

    doing = planned + human if args.include_human else planned
    print(f"\n{len(planned)} machine rows, {len(human)} author rows, {len(refused)} refused.")
    if not args.apply:
        print(f"Dry run. {len(doing)} rows would be written.")
        return 0

    written = 0
    for row_id, label, before, after, _named in doing:
        result = session.execute(
            sql("UPDATE content_versions SET text = :after WHERE id = :id AND text = :before"),
            {"after": after, "id": row_id, "before": before},
        )
        if result.rowcount != 1:
            print(f"SKIPPED  {label}: the row changed underneath us")
            continue
        written += 1
    session.commit()
    print(f"Wrote {written} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
