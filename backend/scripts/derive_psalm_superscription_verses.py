# ruff: noqa: RUF002
# The psalm text quoted in the prose is Cyrillic because that is what it is.
"""Build the table of how many verses a psalm's superscription occupies.

A psalm may carry a heading — "To the choirmaster. A Psalm of David." —
and the editions do not agree on whether that heading is a verse.
English does not number it: ask the Berean Standard Bible for Psalm 51:1
and it answers "Have mercy on me, O God". The Masoretic tradition does
number it, and Psalm 51's heading is two verses long, so an edition that
follows it answers the same request with "Dem Vorsänger. Ein Psalm von
David," — the librarian's note, printed in a lesson that goes on to
explain the plea for mercy standing underneath it.

Which editions this platform quotes, and what they do
-----------------------------------------------------
Measured against the live catalogue on 2026-08-22, over the twelve
Daily Challenge questions that cite a psalm:

* Elberfelder (de) numbers the heading. Psalms 8, 19, 22 and 51 came
  back as *nothing but* the heading — four questions whose explanation
  discusses a verse the reader was never shown — and Psalms 23, 103,
  110, 121 and 139 came back with the heading welded to the front of
  the verse, because in those psalms the heading shares verse 1 with
  the opening line.
* Куліш (uk) does the same, in the same nine psalms.
* НРТ (ru) does it too, and has done since the Septuagint table
  landed: that table carries this shift already, because the Slavic
  numbering it maps into is Masoretic in its verses.
* The English editions are the platform's reference system and are
  therefore the thing everything else is measured against.

So the table below is the *second* half of the same fact the Septuagint
table records, split out for the two editions that keep Hebrew chapter
numbers and Masoretic verse numbers at the same time.

Where the numbers come from
---------------------------
The same file, read the same way. ``data/synodal-ru.json`` is keyed by
the English reference and carries the Slavic verse number of each piece
inline, so an English verse 1 that holds three Slavic verses says so::

    psalms.51.1 -> (50-1) Начальнику хора. Псалом Давида,
                   (50-2) Когда приходил к нему пророк Нафан…
                   (50-3) Помилуй меня, Боже…

Count the pieces and take one away: the last of them is the psalm, and
everything before it is the heading. Psalm 51 has three, so its heading
is two verses and English 51:1 is verse 3 of an edition that numbers it.
Psalm 23 has one —

    psalms.23.1 -> (22-1) Псалом Давида. Господь--Пастырь мой…

— heading and opening line sharing a verse, so the offset is nought and
Psalm 23:1 is Psalm 23:1 in every edition here.

A piece standing before the first marker counts too. Psalm 8 reads
``Начальнику хора… (8-2) Господи, Боже наш!``: the heading has no marker
of its own because it is the one verse whose number both systems agree
on, and dropping it would make the psalm's heading disappear.

The rule needs no exceptions, which is the reason it is this rule and
not the ``^^…^^`` markers the file also carries. Those mark the heading
directly and would be the obvious thing to read — but in Psalms 51, 52,
54 and 60 the closing ``^^`` sits at the end of the whole entry rather
than at the end of the heading, and a derivation that trusted it called
those four headings three verses long. Counting pieces does not depend
on that markup at all. It also answers the psalms the Septuagint table
cannot: Hebrew 10 is not a separate psalm there and its first verse is
Slavic 9:22, which as an offset would read twenty-one — while as a count
of pieces it reads one piece, no heading, nought.

Use
---
  python -m scripts.derive_psalm_superscription_verses          # rewrite
  python -m scripts.derive_psalm_superscription_verses --check  # verify
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "app" / "services" / "bible" / "data"
SOURCE = DATA / "synodal-ru.json"
TABLE = DATA / "psalm_superscription_verses.json"

_MARKER = re.compile(r"\(\d+-\d+\)")

PSALM_COUNT = 150


def superscription_verses(entry: str) -> int:
    """How many whole numbered verses this psalm's heading occupies.

    Zero for a psalm with no heading, and zero for a heading that shares
    its verse with the opening line — both mean an edition numbering the
    heading still answers verse 1 with the words a reader citing verse 1
    came for.
    """
    markers = list(_MARKER.finditer(entry))
    leading = not markers or bool(entry[: markers[0].start()].strip())
    pieces = len(markers) + (1 if leading else 0)
    return max(0, pieces - 1)


def build() -> dict[str, int]:
    verses: dict[str, str] = json.loads(SOURCE.read_text(encoding="utf-8"))
    table: dict[str, int] = {}
    for chapter in range(1, PSALM_COUNT + 1):
        entry = verses.get(f"psalms.{chapter}.1")
        if entry is None:
            continue
        offset = superscription_verses(entry)
        if offset:
            table[str(chapter)] = offset
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the checked-in table has drifted")
    args = parser.parse_args()

    table = build()
    rendered = json.dumps(table, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if args.check:
        if not TABLE.exists() or TABLE.read_text(encoding="utf-8") != rendered:
            print("psalm_superscription_verses.json has drifted from the Synodal source", file=sys.stderr)
            return 1
        print(f"table is current: {len(table)} psalms carry a numbered heading")
        return 0
    TABLE.write_text(rendered, encoding="utf-8")
    print(f"wrote {TABLE} — {len(table)} psalms carry a numbered heading")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
