# ruff: noqa: RUF002
"""Close the quotations that were served opened at both ends.

Thirty-one live German and Ukrainian rows carry a quotation whose
closing mark is written as an opening one, so the reader meets a
quotation that opens twice and never ends:

    2. Mose 20,1 besagt: „Und Gott redete alle diese Worte und sprach:„
    Вихід 20:1 свідчить: «І глаголав Господь всї словеса оцї, глаголючи:«

Every one is Scripture cut where the question needed it, so the verse
ends in the punctuation it ends in — a colon, an ellipsis, or a stray
dash — and ``_OPENING_CONTEXT`` read that punctuation as an invitation
to open. The rule is fixed in ``services/translation/typography.py``;
this script mends the rows that were written before the fix.

The repair is ``normalize_typography`` itself. It is pure, it needs no
model and no network, and it is idempotent, so no re-translation is
involved and running this twice is the same as running it once.

What it refuses
---------------
Re-pointing a whole row would sweep in every other rule the module has
learned since the row was written — a German reference respelled, an
English title re-cased, a thousands separator inserted. Measured on
2026-08-21, that is 305 live rows, and 268 of them have nothing to do
with an unclosed quotation. So each row must pass three tests or it is
reported and left alone:

* **the row must already be pointed in this language's own marks** —
  every mark in it is already ``«`` or ``»``, ``„`` or ``“``, merely
  facing the wrong way. A row still carrying straight quotes is a
  different job, and the dry run found why it matters: a Russian row
  reading ``«“…”»`` — an inner quotation set the way Russian sets one —
  passes a naive pair test only after being flattened to ``««…»»``,
  which is a regression dressed as a repair;
* **the marks must be repaired** — the sequence of quotation marks must
  go from one that cannot pair to one that nests correctly;
* **nothing but a mark may move** — the text must be the same length and
  every character that differs must be a quotation mark on both sides,
  which is what proves the UPDATE carries no other rule with it;
* **the result must be a fixed point** — pointing it again changes
  nothing.

Rows whose ``origin`` is ``human`` are reported separately and skipped
by default. Their text is what ``daily_challenge/translate.py`` hashes
to decide whether a machine translation is stale, so editing one
reopens every locale of that field for re-translation — a real cost,
and a decision for a person rather than for this script.

Use
---
  python -m scripts.repoint_unclosed_quotations            # dry run, prints the plan
  python -m scripts.repoint_unclosed_quotations --apply    # do it
  python -m scripts.repoint_unclosed_quotations --apply --include-human
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text as sql
from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.schemas.locale import QUOTATION_MARKS
from app.services.translation.staged_pipeline import _content_kind_of
from app.services.translation.typography import _QUOTE_CHARS, _prose_mask, normalize_typography

_LOCALES = ("de", "uk", "ru", "en")


def _prose_marks(value: str) -> list[str]:
    free, _ = _prose_mask(value)
    return [char for index, char in enumerate(value) if free[index] and char in _QUOTE_CHARS]


def _marks_pair_up(marks: list[str], opening: str, closing: str) -> bool:
    """The marks read as a bracket language: opening pushes, closing pops.

    A language whose two marks are the same character cannot be read
    this way, so an even count is all that can be asked of it.
    """
    if opening == closing:
        return len(marks) % 2 == 0
    depth = 0
    for mark in marks:
        if mark == opening:
            depth += 1
        elif mark == closing:
            depth -= 1
            if depth < 0:
                return False
        else:
            # A straight quote the pass declined to touch. Not repaired
            # here, and not something to call well formed either.
            return False
    return depth == 0


def _only_marks_moved(before: str, after: str) -> bool:
    """True when the two strings differ in quotation marks and nothing else."""
    if len(before) != len(after):
        return False
    return all(a == b or (a in _QUOTE_CHARS and b in _QUOTE_CHARS) for a, b in zip(before, after, strict=True))


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
    refused: list[tuple[str, str, str]] = []
    human: list[tuple[str, str, str, str]] = []

    for row in rows:
        kind = _content_kind_of(row.entity_type, row.field)
        pointed = normalize_typography(row.text, row.locale, content_kind=kind)
        if pointed == row.text:
            continue
        opening, closing = QUOTATION_MARKS[row.locale]
        before_marks = _prose_marks(row.text)
        if any(mark not in (opening, closing) for mark in before_marks):
            continue  # not yet pointed in this language's marks: a different job
        was_broken = not _marks_pair_up(before_marks, opening, closing)
        now_pairs = _marks_pair_up(_prose_marks(pointed), opening, closing)
        if not (was_broken and now_pairs):
            continue  # not this defect: some other rule wants this row, and not today
        label = f"[{row.locale}] {row.entity_type}.{row.field} {row.id}"
        if not _only_marks_moved(row.text, pointed):
            refused.append((label, "more than a quotation mark would move", row.text))
            continue
        if normalize_typography(pointed, row.locale, content_kind=kind) != pointed:
            refused.append((label, "the result is not a fixed point", row.text))
            continue
        target = human if row.origin == "human" else planned
        target.append((str(row.id), label, row.text, pointed))

    for label, why, _text in refused:
        print(f"REFUSED  {label}: {why}")
    for _id, label, before, after in human:
        print(f"HUMAN    {label}: {''.join(_prose_marks(before))} -> {''.join(_prose_marks(after))}")
    for _id, label, before, after in planned:
        print(f"REPAIR   {label}: {''.join(_prose_marks(before))} -> {''.join(_prose_marks(after))}")

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
