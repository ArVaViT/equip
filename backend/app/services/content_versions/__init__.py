"""Single-point-of-mutation helpers for ``content_versions``.

Every write to the table goes through here. Direct INSERTs or
UPDATEs from anywhere else in the codebase are forbidden — the
supersession + cascade-invalidation invariants only hold when they
all funnel through ``record_human_version`` / ``record_mt_version``
/ ``record_mt_failure``.
"""

from app.services.content_versions.write import (
    record_human_version,
    record_mt_failure,
    record_mt_version,
)

__all__ = [
    "record_human_version",
    "record_mt_failure",
    "record_mt_version",
]
