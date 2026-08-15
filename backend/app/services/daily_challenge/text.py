"""Text resolution for Daily Challenge questions + options, per language.

Question text + option text + explanation all live in
``content_versions``. The pattern mirrors what the quiz tree does in
``app/services/translation/resolve_for_display.py`` — three calls to
``fetch_cv_entity_texts_with_fallback`` (one per entity_type) so each
gets its own ``fields=[...]`` list and the SQL is one tuple-IN per type.

There is no tier order any more. ``fetch_cv_entity_texts_with_fallback``
serves the ``display_locale`` row and nothing else while translation is
configured: a reader who chose German is not shown Russian because the
German row is late. What that leaves — an empty string — is not
renderable either, which is what ``QuestionTextBundle.is_servable``
exists to say out loud.

For the editor's ``?source=1`` view we'd set
``prefer_human=True`` so an MT row never masks a human-authored source.
The Sprint 2 endpoints don't expose ``?source=1`` (editorial flows land
in Sprint 3); this helper keeps the parameter for future use.
"""

from __future__ import annotations

import uuid  # noqa: TC003 — used at runtime by dataclass annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.schemas.locale import LocaleCode, normalize_locale
from app.services.content_versions import fetch_cv_entity_texts_with_fallback

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.daily_challenge import DailyChallengeQuestion


@dataclass(frozen=True, slots=True)
class QuestionTextBundle:
    """Resolved texts for one question + its options, in one language.

    ``options`` maps the option's ``id`` to its locale-resolved text.
    Missing ids resolve to ``None`` — the caller decides whether to
    treat that as a render fallback or a hard error.
    """

    question_text: str
    explanation: str | None
    options: dict[uuid.UUID, str]

    @property
    def is_servable(self) -> bool:
        """Whether this is a question a person can actually answer.

        Since the fallback chain was removed, a locale with no rows
        resolves to empty strings rather than to somebody else's
        language. Empty strings render: the card appears, with no
        question and four blank buttons, and the reader is invited to
        answer nothing. That is worse than an absent card, because it
        looks like a bug in their browser rather than a gap in ours.

        The explanation is not part of the test — it is nullable by
        design, and a question with none is still answerable.
        """
        if not self.question_text.strip():
            return False
        return all(text.strip() for text in self.options.values())


def fetch_question_text_bundle(
    db: Session,
    *,
    question: DailyChallengeQuestion,
    display_locale: LocaleCode,
    prefer_human: bool = False,
) -> QuestionTextBundle:
    """Resolve the bilingual texts for a fully-loaded question +
    its options. The caller passes the ORM row with ``options``
    already loaded (via ``selectinload`` in the schedule helper)."""
    source_locale: LocaleCode = normalize_locale(question.source_locale)

    question_texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="daily_challenge_question",
        entity_ids=[str(question.id)],
        fields=["question_text", "explanation"],
        display_locale=display_locale,
        source_locale=source_locale,
        prefer_human=prefer_human,
    )
    question_text = question_texts.get((str(question.id), "question_text")) or ""
    explanation = question_texts.get((str(question.id), "explanation"))

    option_ids = [str(o.id) for o in question.options]
    if option_ids:
        option_texts = fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="daily_challenge_option",
            entity_ids=option_ids,
            fields=["option_text"],
            display_locale=display_locale,
            source_locale=source_locale,
            prefer_human=prefer_human,
        )
    else:
        option_texts = {}

    options_map: dict[uuid.UUID, str] = {}
    for opt in question.options:
        resolved = option_texts.get((str(opt.id), "option_text")) or ""
        options_map[opt.id] = resolved

    return QuestionTextBundle(
        question_text=question_text,
        explanation=explanation,
        options=options_map,
    )
