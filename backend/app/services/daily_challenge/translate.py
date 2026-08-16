"""The Daily Challenge is platform content, and platform content is not
exempt from speaking every language.

Course content translates itself: an edit calls ``reconcile_entity``,
which finds the entity's course, reads its declared language, and fans
out to the rest. A Daily Challenge question has no course — it is a
platform-wide rotation — so ``reconcile_entity`` returns an empty report
for it, by design, and until now nothing else picked the slack up.

What kept it working was an accident of how the questions are made: the
generator's fourth round produces a Russian rendering alongside the
English one and writes both into ``content_versions``. Two languages
arrived because two languages were generated, not because anything
translated anything. When German and Ukrainian shipped, no round
produced them and no pipeline asked for them. On 2026-08-15 that was 490
questions in production with 980 English rows, 988 Russian ones, and
zero in either new language — which a German reader saw as a challenge
card with an empty question and four blank buttons, every day.

This module is the fan-out that was missing. It reads each question's
source text out of ``content_versions`` (the columns were dropped when
the content moved there) and hands the question and its options to the
same orchestrator every other entity goes through — same validation,
same ``needs_review`` gate, same idempotence by ``source_hash``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.schemas.locale import LOCALE_CODES, LocaleCode, normalize_locale
from app.services.translation.completeness import TranslationCompleteness, completeness_of
from app.services.translation.orchestrator import (
    OrchestratorReport,
    TranslationFieldSpec,
    translate_entity_fields,
)
from app.services.translation.protocol import EntityType
from app.services.translation.registry import entity_field_specs
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.daily_challenge import DailyChallengeQuestion
    from app.services.translation.protocol import TranslationProvider

logger = logging.getLogger(__name__)

# One orchestrator call's worth of work: what to translate, which rows
# it lands in, and the sentence the model is given for context.
QuestionPart = tuple[EntityType, str, list[TranslationFieldSpec], str]

_QUESTION_CONTEXT = "Bible question for the Equip Daily Challenge."
_OPTION_CONTEXT = "Answer option for an Equip Daily Challenge question."


def _question_parts(
    db: Session,
    question: DailyChallengeQuestion,
) -> list[QuestionPart]:
    """The question and each of its options, with their translatable
    fields resolved: ``(entity_type, entity_id, field_specs, context)``.

    Options are separate rows in ``content_versions`` and therefore
    separate orchestrator calls; keeping them in one list means the
    caller never translates a question without its answers, which would
    leave a reader a legible question and four blanks — worse than
    nothing, because it looks answerable.
    """
    source: LocaleCode = normalize_locale(question.source_locale)
    parts: list[QuestionPart] = []

    question_fields = entity_field_specs(db, "daily_challenge_question", question, source)
    if question_fields:
        parts.append(("daily_challenge_question", str(question.id), question_fields, _QUESTION_CONTEXT))

    for option in sorted(question.options, key=lambda o: o.order_index):
        option_fields = entity_field_specs(db, "daily_challenge_option", option, source)
        if option_fields:
            parts.append(("daily_challenge_option", str(option.id), option_fields, _OPTION_CONTEXT))

    return parts


def translate_question(
    db: Session,
    question: DailyChallengeQuestion,
    *,
    provider: TranslationProvider | None = None,
) -> OrchestratorReport:
    """Translate one question and its options into every served locale.

    Idempotent: ``translate_entity_fields`` short-circuits on an
    unchanged ``source_hash``, so calling this on an already-translated
    question costs no provider calls. Safe to run on every question in
    the pool, and cheap enough to run after every edit.
    """
    if not is_translation_enabled():
        return OrchestratorReport()

    source: LocaleCode = normalize_locale(question.source_locale)
    total = OrchestratorReport()
    for entity_type, entity_id, fields, context in _question_parts(db, question):
        report = translate_entity_fields(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            source_locale=source,
            fields=fields,
            context=context,
            provider=provider,
        )
        total = OrchestratorReport(
            translated=total.translated + report.translated,
            skipped=total.skipped + report.skipped,
            failed=total.failed + report.failed,
            needs_review=total.needs_review + report.needs_review,
        )

    logger.info(
        "daily challenge question %s translated=%d skipped=%d failed=%d needs_review=%d",
        question.id,
        total.translated,
        total.skipped,
        total.failed,
        total.needs_review,
    )
    return total


def question_translation_completeness(
    db: Session,
    question: DailyChallengeQuestion,
) -> TranslationCompleteness:
    """Is this question servable in every language the platform serves?

    The same question the publication gate asks of a course, asked of a
    single question — and answered by the same code, so the two cannot
    drift into disagreeing about what "translated" means.
    """
    if not is_translation_enabled():
        return TranslationCompleteness(required=0, present=0, gaps=())

    wanted: dict[tuple[str, str, str], set[str]] = {}
    for entity_type, entity_id, fields, _context in _question_parts(db, question):
        for spec in fields:
            targets: set[str] = {code for code in LOCALE_CODES if code != spec.source_locale}
            if targets:
                wanted[(entity_type, entity_id, spec.field)] = targets
    return completeness_of(db, wanted)


def questions_missing_a_language(db: Session, *, limit: int) -> list[DailyChallengeQuestion]:
    """Questions with work outstanding in some locale.

    Two things put a question here: a locale with no ``question_text``
    row at all, and a row of any field still sitting at ``failed``.

    The first half used to be the whole of it, described as a cheap
    prefilter that a later pass would correct. There is no later pass —
    this is the only thing that selects work, so what it missed was
    missed permanently. The gate that decides what a reader may see is
    ``question_translation_completeness``; this decides what ever gets
    looked at again.

    "Has a settled row" rather than "has a good row", and the
    difference is the whole behaviour of the sweep. A row parked at
    ``needs_review`` is not retried by the orchestrator — the model runs
    at temperature 0, so asking again returns the same text and the same
    verdict. Counting those as missing put the sweep in a loop: the same
    two questions selected every night, every field skipped, no
    progress, and the day's budget spent on questions a person has to
    look at anyway.

    ``failed`` is the exception, because it is the one status the
    orchestrator does retry. It is also what
    ``POST /admin/translations/retry-reviewed`` leaves behind when an
    operator re-opens rows after a prompt or validator change — so
    treating it as settled would mean the sweep never went back for
    exactly the rows somebody just asked it to redo.
    """
    from app.models.content_version import ContentVersion, ContentVersionStatus
    from app.models.daily_challenge import DailyChallengeOption, DailyChallengeQuestion

    # The two sides are compared in Python, not in SQL:
    # ``content_versions.entity_id`` is text while a question's id is a
    # uuid, and the dialects disagree about what that comparison means.
    # Postgres refuses it; SQLite accepts it and matches nothing, which
    # is the worse failure — the sweep would call every question
    # untranslated forever and re-translate the same rows every night.
    complete: set[str] = {
        row[0]
        for row in db.query(ContentVersion.entity_id)
        .filter(
            ContentVersion.entity_type == "daily_challenge_question",
            ContentVersion.field == "question_text",
            ContentVersion.superseded_by.is_(None),
            # ``failed`` is the one status the orchestrator retries, so a
            # row sitting in it is not a language that has been dealt
            # with — it is work waiting. This is also how a row re-opened
            # by ``POST /admin/translations/retry-reviewed`` finds its way
            # back into the sweep: the endpoint parks it at ``failed``,
            # and without this the question would look settled and never
            # be picked up again.
            ContentVersion.status != ContentVersionStatus.FAILED,
        )
        .group_by(ContentVersion.entity_id)
        .having(func.count(func.distinct(ContentVersion.locale)) >= len(LOCALE_CODES))
        .all()
    }

    # A question is not settled because its *question text* is settled.
    #
    # Counting one field was described as a cheap prefilter that a later
    # pass would correct, and there is no later pass — this is the only
    # thing that selects work. On 2026-08-16 that meant 57 explanations
    # carrying an English KJV quotation inside German and Ukrainian prose
    # sat at ``failed`` while the sweep reported "nothing left to
    # translate", because every one of those questions had its four
    # question_text rows in place. They were invisible, and would have
    # stayed invisible.
    #
    # So anything still marked ``failed`` — on either field, or on any of
    # the question's answer options — takes its question back out of the
    # settled set.
    unsettled: set[str] = {
        row[0]
        for row in db.query(ContentVersion.entity_id)
        .filter(
            ContentVersion.entity_type == "daily_challenge_question",
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == ContentVersionStatus.FAILED,
        )
        .distinct()
        .all()
    }
    failed_option_ids: set[str] = {
        row[0]
        for row in db.query(ContentVersion.entity_id)
        .filter(
            ContentVersion.entity_type == "daily_challenge_option",
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == ContentVersionStatus.FAILED,
        )
        .distinct()
        .all()
    }
    if failed_option_ids:
        # Compared in Python for the reason given above: an option id is
        # text on one side of this and a uuid on the other, and asking
        # the database to bridge that is a dialect-dependent answer —
        # Postgres refuses it, SQLite silently matches nothing. The
        # second is what would hurt: this branch would go back to doing
        # nothing at all, and look like it worked.
        unsettled |= {
            str(question_id)
            for option_id, question_id in db.query(DailyChallengeOption.id, DailyChallengeOption.question_id).all()
            if str(option_id) in failed_option_ids
        }
    complete -= unsettled

    # Oldest first: the questions already in the schedule are the ones a
    # reader hits first, and they were created first.
    candidates = [
        row[0]
        for row in db.query(DailyChallengeQuestion.id)
        .filter(DailyChallengeQuestion.rejected.is_(False))
        .order_by(DailyChallengeQuestion.created_at)
        .all()
    ]
    pending = [qid for qid in candidates if str(qid) not in complete][:limit]
    if not pending:
        return []

    by_id = {
        question.id: question
        for question in db.query(DailyChallengeQuestion)
        .options(selectinload(DailyChallengeQuestion.options))
        .filter(DailyChallengeQuestion.id.in_(pending))
        .all()
    }
    return [by_id[qid] for qid in pending if qid in by_id]


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What one sweep repaired. ``questions`` is what was actually
    touched, not the limit that was offered — a caller logging the limit
    would report steady progress on an empty backlog."""

    questions: int
    rows: OrchestratorReport


def translate_pending_questions(
    db: Session,
    *,
    limit: int = 2,
    provider: TranslationProvider | None = None,
) -> SweepReport:
    """Translate up to ``limit`` questions that are missing a language.

    The sweep that makes the rest of this module self-healing. New
    questions are translated when they are generated; this catches the
    ones that were written before a language existed, the ones whose
    source text was edited afterwards, and the ones whose provider call
    failed on the day. Called once per worker tick with a small limit so
    a day's translation work stays inside the same modest Gemini budget
    the generator lives on.
    """
    if not is_translation_enabled():
        return SweepReport(questions=0, rows=OrchestratorReport())

    total = OrchestratorReport()
    pending = questions_missing_a_language(db, limit=limit)
    for question in pending:
        report = translate_question(db, question, provider=provider)
        total = OrchestratorReport(
            translated=total.translated + report.translated,
            skipped=total.skipped + report.skipped,
            failed=total.failed + report.failed,
            needs_review=total.needs_review + report.needs_review,
        )
    return SweepReport(questions=len(pending), rows=total)


__all__ = [
    "SweepReport",
    "question_translation_completeness",
    "questions_missing_a_language",
    "translate_pending_questions",
    "translate_question",
]
