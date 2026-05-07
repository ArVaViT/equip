"""Translation pipeline: provider-agnostic interface with a Gemini default.

Public surface (re-exported here):

    >>> from app.services.translation import (
    ...     TranslationProvider,
    ...     TranslationRequest,
    ...     TranslationResult,
    ...     get_translation_provider,
    ...     compute_source_hash,
    ... )

The provider layer is abstract on purpose: every API call goes through
``TranslationProvider.translate()`` so we can swap Gemini for OpenAI,
Anthropic, or a self-hosted model with one config change. See
``docs/multilingual-and-translation-notes.txt`` for the rollout plan.
"""

from app.services.translation.hash import compute_source_hash
from app.services.translation.protocol import (
    ContentKind,
    EntityType,
    TranslationError,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)
from app.services.translation.service import (
    NoopTranslationProvider,
    get_translation_provider,
    is_translation_enabled,
)

__all__ = [
    "ContentKind",
    "EntityType",
    "NoopTranslationProvider",
    "TranslationError",
    "TranslationProvider",
    "TranslationRequest",
    "TranslationResult",
    "compute_source_hash",
    "get_translation_provider",
    "is_translation_enabled",
]
