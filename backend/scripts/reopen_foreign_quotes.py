# ruff: noqa: RUF002
# Scripture quoted in the prose is Cyrillic because that is the defect.
"""Find translations that quote Scripture in the wrong language, and ask for them again.

The whole string reads as the language it is filed under, so the
detector is satisfied and the row is ``ok``. Inside it, in quotation
marks, sits a verse in another language::

    Johannes 3:17 besagt: 'For God did not send his Son into the world…'
    In Genesis 3:1, the serpent begins by asking, 'подлинно ли сказал Бог…'

That is what a missed verse substitution looks like from the reader's
side. The prompt tells the model to leave quoted Scripture untouched —
rightly, the alternative is a model reciting Scripture from memory — so
when the substitution layer does not recognise the quotation, the source
language's verse travels into every translation intact.

The layer recognises these now. The rows written before it did are still
in the database, and nothing selects them: they are ``ok``, their source
has not changed, and every gap-finder considers them done.

Why this is a script and not a validation rule
----------------------------------------------
Measured against the whole store on 2026-08-16: 31 accepted rows have a
quotation in another language, and **13 of them are correct**. Those are
the ones where the author is comparing translations on purpose —
"'clear as crystal' (KJV/NIV/NASB) or 'светлую, как кристалл'
(Synodal)" — so a rule that parked every foreign quotation would be
wrong more often than it was right. That is far too high to put in front
of the pipeline, so this reports, splits, and asks; a person reads the
list.

The remainder is not perfectly clean either. One Ukrainian lesson is on
it because the detector read "Не мир прийшов Я принести, а меч" as
Russian, which it is not. Re-translating a good row costs one call and
lands back where it started, so the list is worth applying as it stands
— but it is a list to read, not a verdict.

The split is by whether the text names another translation, because an
author comparing two renderings always says which two. It is a good
signal and not a perfect one, which is why ``--apply`` prints every row
it is about to touch.

What it does to a row
---------------------
Clears ``source_hash``. The orchestrator skips an ``ok`` row whose
source hash is unchanged, so clearing it is what makes the row eligible
again — and unlike parking it at ``failed``, the existing text stays
servable until better text replaces it. A reader is never shown a blank
because we decided to improve something.

Use
---
  python -m scripts.reopen_foreign_quotes            # the list, no writes
  python -m scripts.reopen_foreign_quotes --apply    # ask for them again
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from sqlalchemy import create_engine, text

from app.core.sanitize import html_to_plain_text
from app.services.bible.substitution import _QUOTED_SPAN
from app.services.language_detection import carries_language, detect_locale

# What counts as a quotation is the substitution layer's own definition,
# imported rather than restated: this script exists to find the rows that
# layer did not catch, and it can only answer that honestly if the two
# agree on what a quotation is.

# An author comparing two renderings names them. Nobody writes "one
# translation says X and another says Y" without saying which.
_TRANSLATION_NAMED = re.compile(
    r"KJV|NIV|NASB|ESV|Synodal|Synodale|синодальн|Синодальн|синодальний|Luther|Кулиш|Куліш",
    re.IGNORECASE,
)

# Machine translations only. A human-written row that quotes another
# language is the author quoting another language — their English lesson
# on how to read a word may well cite the Synodal on purpose — and
# clearing its hash would do nothing anyway, because the orchestrator
# never overwrites ``origin='human'``. Listing them as defects was
# simply wrong about whose text it is.
_SQL = text("""
    select id, entity_type, entity_id, field, locale, text
    from content_versions
    where superseded_by is null and status = 'ok' and origin = 'mt'
      and text is not null and text <> ''
""")


def _foreign_quote(body: str, locale: str) -> tuple[str, str] | None:
    """The first quotation that reads as some other language, and which."""
    plain = html_to_plain_text(body)
    for match in _QUOTED_SPAN.finditer(plain):
        quote = match.group("inner")
        if not carries_language(quote):
            continue
        detected = detect_locale(quote)
        if detected is not None and detected != locale:
            return quote, detected
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="clear the source hash so these are translated again")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    engine = create_engine(url)
    reopen: list[str] = []
    deliberate = 0

    with engine.connect() as conn:
        for row in conn.execution_options(stream_results=True).execute(_SQL):
            found = _foreign_quote(row.text, row.locale)
            if found is None:
                continue
            quote, detected = found
            plain = html_to_plain_text(row.text)
            if _TRANSLATION_NAMED.search(plain):
                deliberate += 1
                print(f"KEEP  [{row.locale} quotes {detected}] {row.entity_type}.{row.field} — names a translation")
                print(f"      {plain[:88]}")
                continue
            reopen.append(str(row.id))
            print(f"AGAIN [{row.locale} quotes {detected}] {row.entity_type}.{row.field}")
            print(f"      context: {plain[:88]}")
            print(f"      quote:   {quote[:88]}")

    if args.apply and reopen:
        with engine.begin() as conn:
            conn.execute(
                text("update content_versions set source_hash = null where id::text = any(:ids)"),
                {"ids": reopen},
            )

    print(f"\n{len(reopen)} to translate again, {deliberate} left alone{' — done' if args.apply else ' (dry run)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
