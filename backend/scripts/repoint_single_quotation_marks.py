"""Set in the language's own marks the quotations written in ASCII ones.

Forty-seven live rows quote Scripture between straight ``'`` marks:

    Johannes 1,1 besagt: 'Im Anfang war das Wort…'
    Псалом 121:1 говорить: 'Посходня пісня. Очі мої підношу на гори…'

Every one arrived from an English source that types them that way, and
the typography pass had no rule for a single mark, so it left all of
them. The rule is in ``services/translation/typography.py``; this mends
the rows written before it.

The repair is ``normalize_typography`` itself — pure, no model, no
network, idempotent, so running this twice is running it once.

What it refuses
---------------
Re-pointing a whole row would sweep in every other rule the module has
learned since the row was written. Measured on 2026-08-22 over the
10 144 rows a reader can reach: 56 change under the current pass, and
only 47 of them are this defect. The other nine are rules with their own
arguments and two are things this script must not do — a Russian row
that nests correctly as ``«…“…”…»`` gets flattened to ``«…«…»…»``, and
an English em dash gains spaces. So every row must pass three tests or
it is reported and left alone:

* **only quotation marks may move** — the result must be the same length
  as the row, and every character that differs must be a quotation mark
  on both sides;
* **the mark that moved must be the straight one** — every character
  that differs must have been ``'`` before. That is the whole of this
  defect, and it is what keeps the nested Russian row out: there the
  characters that would move are ``“`` and ``”``;
* **the result must be a fixed point** — pointing it again must change
  nothing, or the row is not settled and this is not the pass to settle
  it.

Usage::

  python -m scripts.repoint_single_quotation_marks            # dry run
  python -m scripts.repoint_single_quotation_marks --apply
  python -m scripts.repoint_single_quotation_marks --apply --include-human
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text as sql
from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.services.translation.staged_pipeline import _content_kind_of
from app.services.translation.typography import _QUOTE_CHARS, normalize_typography

_LOCALES = ("de", "uk", "ru", "en")

#: The character this repair exists for, and the only one it may move.
_STRAIGHT = "'"


def _only_straight_marks_moved(before: str, after: str) -> bool:
    """True when the two strings differ only where a straight single mark
    became one of the language's quotation marks."""
    if len(before) != len(after):
        return False
    return all(was == now or (was == _STRAIGHT and now in _QUOTE_CHARS) for was, now in zip(before, after, strict=True))


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
            SELECT id, entity_type, entity_id, field, locale, origin, text
            FROM content_versions
            WHERE superseded_by IS NULL AND status = 'ok' AND locale = ANY(:locales)
            """
        ),
        {"locales": list(_LOCALES)},
    ).all()

    planned: list[tuple[str, str, str, str]] = []
    human: list[tuple[str, str, str, str]] = []
    refused: list[tuple[str, str]] = []

    for row in rows:
        kind = _content_kind_of(row.entity_type, row.field)
        pointed = normalize_typography(row.text, row.locale, content_kind=kind)
        if pointed == row.text:
            continue
        label = f"[{row.locale}] {row.entity_type}.{row.field} {row.id}"
        if not _only_straight_marks_moved(row.text, pointed):
            # Not this defect. Silent rather than reported: the pass has
            # a dozen rules and most rows it wants to touch are none of
            # this script's business.
            continue
        if normalize_typography(pointed, row.locale, content_kind=kind) != pointed:
            refused.append((label, "the result is not a fixed point"))
            continue
        (human if row.origin == "human" else planned).append((str(row.id), label, row.text, pointed))

    for label, why in refused:
        print(f"REFUSED  {label}: {why}")
    for verb, batch in (("HUMAN ", human), ("REPAIR", planned)):
        for _id, label, before, after in batch:
            at = before.find(_STRAIGHT)
            print(f"{verb}   {label}")
            print(f"           …{before[max(0, at - 40) : at + 60]}…")
            print(f"        -> …{after[max(0, at - 40) : at + 60]}…")

    doing = planned + human if args.include_human else planned
    print(f"\n{len(planned)} machine rows, {len(human)} author rows, {len(refused)} refused.")
    if not args.apply:
        print(f"Dry run. {len(doing)} rows would be written.")
        return 0

    written = 0
    for row_id, label, before, after in doing:
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
