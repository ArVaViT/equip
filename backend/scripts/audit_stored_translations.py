"""Read every translation in the database and ask whether it is fit to serve.

The validator runs once, when a translation is written, against the
rules that existed that day. Rules change: the detector's thresholds
moved after being measured, the reference comparison learned that a
German Bible writes 3,16, the substitution layer learned to recognise a
quotation inside a sentence. Rows written before a rule existed were
never asked the question, and rows parked by a rule that turned out to
be wrong were never asked again.

So this walks the whole store and re-asks — cheaply, with no provider
calls — reporting four things the reader would notice:

* ``marker_leaked``     — a ``VERSE_`` sentinel reached the stored text.
                          The reader sees ``VERSE_a3f9c2`` where a verse
                          belongs. This is the one that must be zero.
* ``wrong_language``    — the text does not read as the language it is
                          filed under. Sampled by the detector, which
                          refuses to guess, so anything it names is
                          worth a look.
* ``identical``         — the translation is character-for-character its
                          source. Sometimes correct (a name, a number),
                          usually not.
* ``markup_broken``     — the translation lost or invented HTML tags.

Use
---
  python -m scripts.audit_stored_translations            # summary
  python -m scripts.audit_stored_translations --samples 5 # with examples

Needs ``DATABASE_URL``. Read-only: it opens one connection, streams the
rows, and writes nothing.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys

from sqlalchemy import create_engine, text

from app.core.sanitize import html_to_plain_text, strip_tags
from app.services.language_detection import carries_language, detect_locale
from app.services.translation.validation import _MARKER_RE, _tag_names

_SQL = text("""
    select t.id, t.entity_type, t.field, t.locale, t.origin, t.status,
           s.locale as source_locale, s.text as source_text, t.text as text
    from content_versions t
    left join content_versions s on s.id = t.source_version_id
    where t.superseded_by is null and t.text is not null and t.text <> ''
""")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2, help="examples to print per finding kind")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    counts: collections.Counter[str] = collections.Counter()
    by_kind: dict[str, list[str]] = collections.defaultdict(list)
    total = 0

    engine = create_engine(url)
    with engine.connect() as conn:
        for row in conn.execution_options(stream_results=True).execute(_SQL):
            total += 1

            if _MARKER_RE.search(row.text):
                counts["marker_leaked"] += 1
                by_kind["marker_leaked"].append(f"{row.entity_type}.{row.field} [{row.locale}] {row.text[:90]}")

            plain = html_to_plain_text(row.text)
            if carries_language(plain):
                detected = detect_locale(plain)
                if detected is not None and detected != row.locale:
                    counts["wrong_language"] += 1
                    by_kind["wrong_language"].append(
                        f"{row.entity_type}.{row.field} filed {row.locale}, reads {detected}: {plain[:80]}"
                    )

            if row.source_text and row.source_locale and row.source_locale != row.locale:
                if strip_tags(row.source_text).strip() == strip_tags(row.text).strip():
                    counts["identical"] += 1
                    by_kind["identical"].append(f"{row.entity_type}.{row.field} [{row.locale}] {plain[:80]}")
                if sorted(_tag_names(row.source_text)) != sorted(_tag_names(row.text)):
                    counts["markup_broken"] += 1
                    by_kind["markup_broken"].append(f"{row.entity_type}.{row.field} [{row.locale}] {plain[:80]}")

    print(f"{total} stored texts\n")
    for kind in ("marker_leaked", "wrong_language", "identical", "markup_broken"):
        print(f"{kind:16} {counts[kind]}")
        for sample in by_kind[kind][: args.samples]:
            print(f"                 {sample}")
    print()
    # A leaked marker is the only one that is never acceptable.
    return 1 if counts["marker_leaked"] else 0


if __name__ == "__main__":
    sys.exit(main())
