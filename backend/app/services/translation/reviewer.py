"""The reader this pipeline never had.

Everything in `validation.py` checks the shape of an answer: markup
preserved, placeholders returned, numbers intact, length plausible,
language correct. All of it is necessary and none of it reads the
sentence. A translation can pass every check and still say the wrong
thing — production served Ukrainian students a passage in which the
Ethiopian eunuch of Acts 8 was a Pentecostal, and every check was green,
because nothing was malformed. Only a person noticed, and only because
somebody was asked to look.

That is the gap this module closes. A second model reads the source and
the translation together and answers the question a human editor
answers: would this pass as written by someone fluent, and does it say
what the original says. What it objects to goes back to the translator
as a correction, in words, which is the same loop that already fixes
structural defects — and the loop is short by design: one review, one
correction, one re-review, then a person.

Three decisions worth stating, because each could go the other way:

**A separate call, not a bigger prompt.** Asking the translator to
grade its own output gets agreement, not review; the failure modes that
survive are exactly the ones the model cannot see in itself. A fresh
call with only the two texts has no memory of why it chose those words.

**It reports, it does not rewrite.** A reviewer that returns improved
text would be a second translator with no accountability — its output
would go unreviewed. Notes go to the translator, which keeps one
component responsible for the words.

**It must earn its objections.** A reviewer that flags everything is
worth nothing: every row lands in a review queue and a person reads the
catalogue by hand, which is where this project started. So the prompt
demands a concrete defect, names the classes that count, and says
plainly that stylistic preference is not one of them.

**The classes it names must be able to occur.** The first list was
written against a catalogue of three courses on Scripture, and two of
its seven entries said so: a changed biblical reference, a verse the
machine wrote out instead of quoting. On a module about church finance
or contract law neither can happen, and the two slots are not free —
what an editor is told to look for is what an editor looks for, and the
mistranslated legal term, the wrong unit, the dosage off by a decimal
point had no line at all. So the standing list is about translation
defects, the Scripture pair is appended only when the source really
carries a reference, and the detector that decides is the one the
substitution layer already uses. Same for the register line: it used to
name the register ("wrong for a Bible school"), which is an objection
the reviewer cannot check against anything; it now asks whether the
translation's register matches the source's, which is on the page.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.services.bible.references import parse_references

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode
    from app.services.translation.protocol import ContentKind

logger = logging.getLogger(__name__)

#: How many notes are worth carrying back to the translator. A correction
#: naming twelve problems is a rewrite request, and the model treats it
#: as one — it starts again rather than fixing what was named.
MAX_NOTES = 4


@dataclass(frozen=True, slots=True)
class ReviewVerdict:
    """What the reviewer thought, in a form the executor can act on."""

    #: False only when the reviewer named at least one concrete defect.
    #: An unparseable reply, a provider error, a timeout — all mean "no
    #: opinion", and no opinion must never block a translation. The
    #: reviewer is an improvement on the pipeline, not a new way for it
    #: to fail.
    acceptable: bool = True
    notes: tuple[str, ...] = ()

    @property
    def has_objections(self) -> bool:
        return not self.acceptable and bool(self.notes)


@runtime_checkable
class TranslationReviewer(Protocol):
    """Anything that can read a translation and object to it."""

    def review(
        self,
        *,
        source: str,
        translation: str,
        source_locale: LocaleCode,
        target_locale: LocaleCode,
        content_kind: ContentKind,
        context: str | None = None,
    ) -> ReviewVerdict: ...


def quotes_scripture(source: str, source_locale: LocaleCode | None) -> bool:
    """Whether this text carries a Bible reference at all.

    The same detection the substitution layer runs before it swaps a
    verse for an ``EQV`` marker — ``bible.references.parse_references``
    is what ``bible.substitution`` calls to decide there is scripture
    here. Reused rather than re-derived: two answers to "is this text
    quoting the Bible" would eventually disagree, and the one in
    ``substitution`` is the one production has been trusting.
    """
    if not source:
        return False
    return bool(parse_references(source, source_locale))


def build_review_prompt(
    *,
    source: str,
    translation: str,
    source_language: str,
    target_language: str,
    content_kind: ContentKind,
    context: str | None,
    source_locale: LocaleCode | None = None,
) -> str:
    """The instruction that decides what this whole layer is worth.

    Written as a brief to an editor rather than a checklist to a
    machine: the classes named below are the ones that actually reached
    production and were caught by a person, and the closing paragraph
    exists because an unconstrained reviewer objects to everything.

    Two of those classes used to be about Scripture and nothing else —
    a changed biblical reference, a verse the machine rendered instead
    of quoting. On a lesson in Acts they are the two that catch the most
    damage. On a module about church finance they are two of seven slots
    spent on something that cannot occur, and every objection slot is
    expensive: a wrong one costs a correction round-trip and a right one
    that was never checked costs a student. So the fixed list names
    defect classes that exist in any subject — a term, a number, a unit,
    a date — and the Scripture pair is appended only when the source
    actually carries a reference. ``quotes_scripture`` decides, using
    the detector the substitution layer already runs.
    """
    context_line = f"\nThis text appears in: {context}\n" if context else ""
    scripture_lines = ""
    if quotes_scripture(source, source_locale):
        scripture_lines = (
            "- a book name or a chapter-and-verse reference changed into a "
            f"different one, or punctuated the way {source_language} "
            f"punctuates it rather than the way a {target_language} Bible "
            "does;\n"
            "- a quoted verse rendered by the machine instead of quoted from "
            f"a {target_language} Bible.\n"
        )
    return (
        f"You are a native {target_language} editor. A "
        f"machine has translated the following from {source_language}. "
        "Judge it the way you would judge a colleague's work before it "
        "reaches students.\n"
        f"{context_line}"
        "\nObject only to something concrete and fixable:\n"
        "- the translation says something the source does not, or leaves "
        "out something the source says;\n"
        "- a name, a term of art, a number, a unit, a date or a citation is "
        "changed into a different one;\n"
        "- grammar a native speaker would not write: wrong gender, wrong "
        "case, a word that does not exist, a sentence that does not parse;\n"
        "- word order or idiom carried over from the source language;\n"
        "- the register does not match the source — the source is plain and "
        "the translation is bureaucratic or academic, the source is formal "
        "and the translation is chatty, or the translation switches how it "
        "addresses the reader mid-text;\n"
        "- typography wrong for this language: quotation marks, "
        "apostrophes, decimal and thousands separators, the way a citation "
        "is punctuated;\n"
        f"{scripture_lines}"
        "\nDo NOT object to a wording you would merely have chosen "
        "differently, to a correct synonym, or to the source text's own "
        "decisions — you are reviewing the translation, not the original. "
        "If it would pass as written by a fluent speaker and says what the "
        "source says, it is acceptable, even if it is not how you would "
        "have put it.\n"
        '\nAnswer with JSON and nothing else: {"acceptable": true} when it '
        'passes, or {"acceptable": false, "problems": ["…", "…"]} where '
        "each problem names what is wrong and what it should be instead, "
        "in English, in one sentence.\n"
        f"\n--- SOURCE ({source_language}) ---\n{source}\n"
        f"\n--- TRANSLATION ({target_language}) ---\n{translation}\n"
    )


def parse_review(reply: str) -> ReviewVerdict:
    """Read the reviewer's answer, and believe nothing it did not say.

    Models wrap JSON in prose and in code fences, and both are handled.
    Anything else — truncation, an apology, a refusal — is treated as no
    opinion rather than as approval or rejection, because guessing in
    either direction is worse than the pipeline as it was.
    """
    if not reply or not reply.strip():
        return ReviewVerdict()

    candidate = reply.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            candidate = candidate[start : end + 1]

    try:
        parsed: Any = json.loads(candidate)
    except (ValueError, TypeError):
        logger.info("reviewer: unparseable reply, treating as no opinion: %s", reply[:120])
        return ReviewVerdict()

    if not isinstance(parsed, dict):
        return ReviewVerdict()
    if parsed.get("acceptable") is not False:
        return ReviewVerdict()

    raw_problems = parsed.get("problems")
    problems: list[str] = []
    if isinstance(raw_problems, list):
        problems = [str(p).strip() for p in raw_problems if str(p).strip()]
    if not problems:
        # Rejected without saying why. There is nothing to send back to
        # the translator, and parking a row on an unexplained objection
        # would put work on a person with no way to act on it.
        logger.info("reviewer: rejected with no problems listed; treating as no opinion")
        return ReviewVerdict()

    return ReviewVerdict(acceptable=False, notes=tuple(problems[:MAX_NOTES]))


__all__ = [
    "MAX_NOTES",
    "ReviewVerdict",
    "TranslationReviewer",
    "build_review_prompt",
    "parse_review",
    "quotes_scripture",
]
