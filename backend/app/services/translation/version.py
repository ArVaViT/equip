# ruff: noqa: RUF002
# Generation 9 is about four spellings of one Cyrillic name, so the entry
# below quotes them. The ambiguous-character lint has nothing to say
# about a Cyrillic letter that is meant to be a Cyrillic letter.
"""Which generation of translation rules is currently in force.

Raise this number whenever a change makes new translations better than
old ones — a glossary entry, a prompt rule, a new correcting pass, a
verse that now resolves to canon instead of to the model.

What happens then needs no further action from anyone: every stored
machine translation made by a lower version is treated exactly like a
missing one, so the reconciler sweep finds it, the queue picks it up,
and the catalogue re-translates itself in the background. Improving
quality is editing a prompt and raising a constant.

What must NOT raise it: a refactor, a rename, a bug fix that changes no
output. Each bump is a full re-translation of everything, and the point
of the number is that it means something.

Raising it is safe while work is in flight. A translation run reads this
once, before its first call, and stamps everything it writes with that
one number — so a pass that was already going when the deploy landed
finishes as the pipeline it started as, whole. What it wrote after the
deploy is below the new number, which is exactly the state the sweep
looks for, so it comes back round and is made again. See
``translation/executor.execute_plan``: the thing that must never happen
is half a batch stamped each way, because both halves look finished.

History
-------
0   Everything made before this was tracked.
1   The glossary (a term is the same term everywhere), per-language
    calque notes, the correcting pass that quotes a rejected wording
    back at temperature 0, answer options included in verse
    substitution, and matching an author's quotation against every
    edition held rather than the first one that answers.
2   The Bible editions quoted to the reader. German moved from Luther
    1912 to Elberfelder, because `daß` and `ward` are not biblical
    register to a German — the 1996 reform abolished them, so they read
    as spelling mistakes. English moved from the bundled King James to
    the Berean Standard Bible, because `spake`, `saith` and `unto`
    appeared in 80 of 252 explanations inside a product that is
    otherwise written in contemporary English. Ukrainian stays on Kulish
    1905, orthography and all: it is the only edition the API offers,
    and a real translation reads better here than a machine rendering
    of one — the owner's call, made 2026-08-19.

    Every stored quotation predates that decision, which is exactly what
    this number is for.
3   The verse placeholder stopped being an English word. It was
    ``VERSE_<hex>``, and a model asked for Ukrainian translated it:
    production holds the same token spelled in Cyrillic letters where
    Scripture belongs — the marker matched nothing on the way back, so the verse
    was dropped and only the reference remained. The prefix is now
    ``EQV``, which is a word in no language we serve. Rows made before
    this are re-fetched because a lost verse cannot be seen by looking
    at them: what is left reads like a finished sentence.
9   A course remembers what it has already called things. Every call
    used to be the first call: nothing translating a field had ever seen
    another field, so one Ukrainian lesson said «у Филиппах» in its
    objectives, «у Филипах» in the heading, «Филиппійська» in the body
    and «у Пилипах» in the questions — four spellings of Philippi, one of
    them the name of a different man. The glossary cannot hold every
    proper noun in every course and was never meant to; twin reuse only
    ever sees identical strings. ``translation/term_memory.py`` reads the
    pairs out of what a course already has and offers them to the next
    field as a preference.

    Rows made before this were made by calls that could not have known,
    which is why the whole corpus is due rather than the lessons somebody
    happened to notice.
10  Three things a reader sees and no check could. A German page now
    writes a Bible reference the way German writes one — ``Apg. 1,8``,
    not ``Деян. 1:8`` left in Cyrillic and not ``Apostelgeschichte 1:8``
    punctuated in Russian; an English title is set in title case; each
    language gets its own quotation marks, apostrophe and dash. A verse
    the author had put in quotation marks gets them back: substitution
    replaced the span the marks stood around, so the quotation came out
    of the machine bare, and 41 quotations in production read as the
    author's own words rather than as Scripture. And a string repeated
    across a course is asked once however different its surroundings,
    which is what stopped «Проверьте себя» being four German headings.

    Stored rows cannot be corrected in place for any of these: the
    reference was rewritten by the model, the quotation marks were
    destroyed before the row was written, and a heading already decided
    is a heading nothing will ask about again.
"""

from __future__ import annotations

from typing import Final

TRANSLATOR_VERSION: Final[int] = 10

__all__ = ["TRANSLATOR_VERSION"]
