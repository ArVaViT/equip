# ruff: noqa: RUF002
# Edition and psalm text quoted in the prose is Cyrillic because that is what it is.
"""Build the Hebrew→Septuagint psalm table from the bundled Synodal text.

The table it writes is checked in, so this script is not part of any
runtime path. It exists so the table is *derived* rather than typed, and
so the derivation can be re-read and argued with.

Where the numbers come from
---------------------------
``data/synodal-ru.json`` is keyed by Hebrew reference — ``psalms.22.1``
is "Боже мой! Боже мой!", which is Hebrew numbering — and each verse
carries inline markers giving the Slavic numbers of the pieces inside
it::

    psalms.22.1 -> (21-1) ^^Начальнику хора…^^ (21-2) Боже мой! Боже мой!…

Two Slavic verses inside one Hebrew verse, because the superscription is
unnumbered in Hebrew and numbered in the Slavic tradition. A reader
citing Psalm 22:1 means the cry, not the heading, so the marker that
counts is the one in front of real text — ``21-2`` — and taking the
first marker instead is how the earlier attempt at this ended up quoting
"Начальнику хора. При появлении зари" to anyone who asked for "My God,
my God, why have you forsaken me".

Why a table and not a formula
-----------------------------
The familiar rule — subtract one from Psalms 10 through 147 — is a
chapter rule, and the disagreement is not only in chapters. Psalm 3 has
the same number in both systems and its verses are still shifted by one.
Psalm 18 shifts its first verse by nothing and the other forty-nine by
one. Psalm 10 does not exist separately in the Slavic tradition at all:
Hebrew 10:1 is Slavic 9:22. No per-chapter offset can say that, and the
one this replaces answered ``None`` for those psalms — refusing to quote
them in Russian rather than quoting them wrongly, which was honest and
still meant a Russian reader saw the author's untranslated verse.

Use
---
  python -m scripts.derive_psalm_numbering            # rewrite the table
  python -m scripts.derive_psalm_numbering --check    # fail if it drifted
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "app" / "services" / "bible" / "data"
SOURCE = DATA / "synodal-ru.json"
TABLE = DATA / "psalm_hebrew_to_septuagint.json"

_MARKER = re.compile(r"\((\d+)-(\d+)\)")


def _slavic_number(text: str) -> str | None:
    """The Slavic number of the verse this entry is.

    Where one Hebrew verse carries several Slavic numbers, the last is
    the verse and the ones before it are the heading. That is not a
    guess: across the whole book, every entry with more than one marker
    is verse 1 of its psalm — 55 of them, and not one anywhere else —
    which is exactly the shape of "the Hebrew tradition leaves the
    superscription unnumbered and the Slavic tradition numbers it".

    The carets the text puts around headings look like the obvious
    signal and are not one. Psalm 38:1 closes its caret before the full
    stop; Psalm 51:1 opens at the heading and closes at the *end of the
    verse*, wrapping the heading and the psalm together. Reading them
    produced a heading's number in both cases — "Начальнику хора. При
    появлении зари" served to a reader who asked for "My God, my God,
    why have you forsaken me".
    """
    markers = _MARKER.findall(text)
    if not markers:
        return None
    chapter, verse = markers[-1]
    return f"{int(chapter)}.{int(verse)}"


def build() -> dict[str, str]:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    table: dict[str, str] = {}
    for key, text in source.items():
        if not key.startswith("psalms."):
            continue
        _, chapter, verse = key.split(".", 2)
        slavic = _slavic_number(text)
        # Psalms 1, 2, 148, 149 and 150 carry no markers because the two
        # systems agree there, verse for verse. Leaving them out of the
        # table is what makes "absent means identical" true.
        if slavic is None or slavic == f"{chapter}.{verse}":
            continue
        table[f"{chapter}.{verse}"] = slavic
    return dict(sorted(table.items(), key=lambda kv: (int(kv[0].split(".")[0]), int(kv[0].split(".")[1]))))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift instead of writing")
    args = parser.parse_args()

    table = build()
    if args.check:
        current = json.loads(TABLE.read_text(encoding="utf-8")) if TABLE.exists() else {}
        if current != table:
            print(f"table has drifted: {len(current)} stored, {len(table)} derived", file=sys.stderr)
            return 1
        print(f"{len(table)} mappings, unchanged")
        return 0

    TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=0, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {len(table)} mappings to {TABLE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
