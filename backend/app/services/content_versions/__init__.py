"""Single-point-of-mutation helpers for ``content_versions``.

Every write to the table goes through ``record_human_version`` /
``record_mt_version`` / ``record_mt_failure``. Direct INSERTs or
UPDATEs from anywhere else in the codebase are forbidden — the
supersession + cascade-invalidation invariants only hold when they
all funnel through these helpers.
"""

from app.services.content_versions.dual_write import dual_write_entity_content
from app.services.content_versions.read import (
    fetch_cv_entity_texts_with_fallback,
    fetch_cv_text_bulk,
)
from app.services.content_versions.write import (
    delete_entity_cv_rows,
    record_human_version,
    record_mt_failure,
    record_mt_version,
)

__all__ = [
    "delete_entity_cv_rows",
    "dual_write_entity_content",
    "fetch_cv_entity_texts_with_fallback",
    "fetch_cv_text_bulk",
    "record_human_version",
    "record_mt_failure",
    "record_mt_version",
]
