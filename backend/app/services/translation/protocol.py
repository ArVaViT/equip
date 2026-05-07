"""Provider-agnostic types for the translation pipeline.

The public contract is intentionally small: ask for one (or many)
text → text translations, get either a result or a typed error. Anything
provider-specific (model id, prompt, retry policy) lives behind the
``TranslationProvider`` implementation.

``ContentKind`` and ``EntityType`` mirror the CHECK-constrained
vocabularies in ``content_translations`` — keeping the literals here (and
re-exporting from ``content_translation`` model) means the same string
set is enforced statically across the API edge, the orchestrator, the
prompt builder, and the ORM column.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

# ``ContentKind`` selects prompt nuances: "plain" for prose, "html" for
# TipTap/HTML chapter blocks, "title" for short headings, "quiz_question"
# / "quiz_option" so the model knows not to expand a single-sentence
# answer into a paragraph. Static checking catches typos at the call site
# rather than letting them silently fall through to the default branch.
ContentKind = Literal[
    "plain",
    "html",
    "title",
    "quiz_question",
    "quiz_option",
]

# Mirrors ``TranslationEntityType`` in ``app.models.content_translation``;
# we re-declare it here (instead of re-exporting) because protocol.py is
# the lower-level module — importing the model here would invert the
# dependency direction. The two literals MUST stay in lockstep with the
# CHECK constraint in ``supabase/migrations/*_content_translations.sql``.
EntityType = Literal[
    "chapter_block",
    "course",
    "module",
    "chapter",
    "quiz",
    "quiz_question",
    "quiz_option",
    "assignment",
    "announcement",
    "course_event",
]


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    """A single unit of work for the translator.

    ``text`` may be plain prose or sanitized HTML — the prompt instructs the
    model to preserve markup verbatim. ``content_kind`` lets us specialize
    handling for known shapes (e.g. quiz options should never expand into
    multiple sentences) without leaking that hint into the database column.
    """

    text: str
    source_locale: LocaleCode
    target_locale: LocaleCode
    content_kind: ContentKind = "plain"
    # Optional contextual hint surfaced to the model as a system note.
    # E.g. "course on the Acts of the Apostles" — improves accuracy on
    # ambiguous theological terms without bloating every row.
    context: str | None = None


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """Successful translation + telemetry."""

    text: str
    # Tokens reported by the provider (``None`` when unavailable).
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Provider-specific model id actually used (so logs can pin a row to a
    # version of the upstream service).
    model: str | None = None


class TranslationError(RuntimeError):
    """Raised when a provider call fails permanently.

    Transient failures (network, 5xx) should be retried inside the provider
    before bubbling up — by the time this reaches the caller the work
    belongs in the failed-rows queue.
    """


@runtime_checkable
class TranslationProvider(Protocol):
    """Minimal surface every concrete provider must implement."""

    name: str

    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Synchronously translate one request. Must be thread-safe."""

    def translate_batch(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        """Translate many requests.

        The convention is to call ``translate()`` per request sequentially;
        ``Protocol`` itself has no default implementation, so concrete
        providers must implement this method (Gemini and Noop both do).
        Providers that support native batching should override with a
        single round-trip implementation for a meaningful speedup.
        """
