"""Stable, content-addressable hash for source strings.

The full SHA-256 hex digest (64 chars) lands in the ``content_translations.
source_hash`` ``VARCHAR(64)`` column — using the full digest (not a
truncated prefix) gives us collision resistance with no storage downside.
Whitespace is collapsed first so trailing-newline-only edits don't mark
every row as ``stale``. The output is deterministic across Python versions
and platforms — vital because the value is persisted next to the
translation and compared on every publish.
"""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Strip & collapse whitespace; preserve case and punctuation otherwise."""
    return _WHITESPACE.sub(" ", text).strip()


def compute_source_hash(text: str, *, locale: str | None = None) -> str:
    """Return the full 64-char SHA-256 hex digest for ``text``.

    ``locale`` participates in the hash so a row with the same text in a
    different source language is treated as a different source — useful when
    a teacher swaps the authoring language mid-course.

    Pre-existing 32-char hashes from older deploys will fail to compare
    equal here; that simply re-translates those rows on the next publish,
    which is acceptable for a young dataset.
    """
    payload = f"{(locale or '').lower()}\x00{_normalize(text)}".encode()
    return hashlib.sha256(payload).hexdigest()
