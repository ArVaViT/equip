"""Copyright-management information, carried through translation verbatim.

A teacher pastes an extract into a lesson and writes under it who wrote it:
a copyright line, «Из книги …», a source label, an ISBN, the URL it came
from. Then the pipeline translates the lesson into three more languages, and
a machine translator has no notion of a line that must not be touched. It
renders the notice into German like any other sentence — or shortens it, or
drops it, because it reads as boilerplate.

That is not a quality problem. 17 U.S.C. § 1202(b) makes it unlawful to
remove or alter copyright-management information — the author's name, the
title, the terms, the identifying number — knowing it will conceal an
infringement. It carries statutory damages per work, it does not depend on
the underlying copying being infringing, and § 512's safe harbour does not
cover it: the safe harbour answers for what users upload, and altering the
notice is the platform's own act. Post University v. Learneo (D. Conn.,
March 2026) put a $75.3m verdict behind that reading, counted per work.

The mechanism is the one already used for Scripture
(``app.services.bible.substitution``), and deliberately so: it is the only
thing in this codebase that has been proved to survive a round trip through
a model. A fragment that looks like copyright-management information is
lifted out before the call, replaced by an ``EQA`` marker, and put back
afterwards character for character. The model never sees it, so it cannot
translate it, shorten it, or decide it is boilerplate.

Restored last
-------------

Later than the Scripture markers, and later than the typography pass. A verse
is restored early on purpose, so the canonical text gets the target language's
quotation marks. A copyright notice must get nothing at all: § 1202 is about
alteration, and re-pointing the quotation marks in a rights line is an
alteration. The last thing that happens to this text is that it comes back
exactly as it was written.

Measured before it was trusted
------------------------------

The obvious rule — "any text containing «Из книги»" — was run against the
production corpus on 2026-09-17: 29,015 rows in ``content_versions``, of
which 39 matched and **all 39 were ordinary prose**. "Geography that repeats
from book to book." "A legal rule from the book of Deuteronomy." Not one was
an attribution. Protecting those would have frozen ordinary sentences in the
source language across four locales, which is its own defect and a visible one.

So the patterns here are anchored rather than substring: a source label has
to open a line and be followed by a colon or a dash; a «Из книги» citation has
to open a line *and* carry a quoted title or a year; a dash-led credit has to
carry a quoted title. Against the same 29,015 rows these match **zero** — no
false positives, and nothing in the corpus today is CMI. This protection is
for what gets pasted next week, and the numbers say what it costs in the
meantime: nothing.
"""

from app.services.attribution.substitution import (
    ATTRIBUTION_MARKER_PREFIX,
    AttributionSpan,
    find_attributions,
    post_substitute,
    pre_substitute,
)

__all__ = [
    "ATTRIBUTION_MARKER_PREFIX",
    "AttributionSpan",
    "find_attributions",
    "post_substitute",
    "pre_substitute",
]
