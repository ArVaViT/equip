"""Bilingual text resolution for Daily Challenge questions + options.

Question text + option text + explanation all live in
``content_versions``. The pattern mirrors what the quiz tree does in
``app/services/translation/resolve_for_display.py`` — three calls to
``fetch_cv_entity_texts_with_fallback`` (one per entity_type) so each
gets its own ``fields=[...]`` list and the SQL is one tuple-IN per type.

Tier order (managed by ``fetch_cv_entity_texts_with_fallback``):

1. ``display_locale`` row.
2. ``source_locale`` row.
3. Any active+ok locale (earliest created — deterministic).

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
    """Resolved bilingual texts for one question + its options.

    ``options`` maps the option's ``id`` to its locale-resolved text.
    Missing ids resolve to ``None`` — the caller decides whether to
    treat that as a render fallback or a hard error.
    """

    question_text: str
    explanation: str | None
    options: dict[uuid.UUID, str]


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
