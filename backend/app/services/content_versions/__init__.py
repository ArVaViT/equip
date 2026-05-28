"""Single-point-of-mutation helpers for ``content_versions`` + the
Phase 2 dual-read comparator.

Every write to the table goes through ``record_human_version`` /
``record_mt_version`` / ``record_mt_failure``. Direct INSERTs or
UPDATEs from anywhere else in the codebase are forbidden — the
supersession + cascade-invalidation invariants only hold when they
all funnel through these helpers.

``compare_resolved_text`` is the Phase 2 dual-read comparator: read
sites call it after running the legacy resolve path; it reads the
same key from ``content_versions`` and returns a structured report
of how the two stores agree (or disagree). It never changes
behaviour — Phase 4 is when reads switch over.
"""

from app.services.content_versions.compare import (
    INTERESTING_REASONS,
    MismatchReason,
    MismatchReport,
    compare_resolved_text,
    get_compare_sample_rate,
    maybe_compare_and_log,
    set_compare_sample_rate,
)
from app.services.content_versions.dual_write import dual_write_entity_content
from app.services.content_versions.read import (
    fetch_cv_course_text_bulk,
    fetch_cv_text_bulk,
)
from app.services.content_versions.write import (
    record_human_version,
    record_mt_failure,
    record_mt_version,
)

__all__ = [
    "INTERESTING_REASONS",
    "MismatchReason",
    "MismatchReport",
    "compare_resolved_text",
    "dual_write_entity_content",
    "fetch_cv_course_text_bulk",
    "fetch_cv_text_bulk",
    "get_compare_sample_rate",
    "maybe_compare_and_log",
    "record_human_version",
    "record_mt_failure",
    "record_mt_version",
    "set_compare_sample_rate",
]
