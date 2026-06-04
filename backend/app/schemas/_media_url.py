"""Shared validator for user-supplied media URLs (course covers, etc.).

A stored media URL is later rendered into an ``<img src>`` / CSS
background on the client. React escapes attribute values, so this is
defence-in-depth rather than the only line — but keeping
``javascript:`` / ``data:`` / ``vbscript:`` and bare ``http://`` out of
the database means a future non-React consumer (an email, an OG-image
renderer, a server-side template) can't be tricked by a value that was
never validated at write time.
"""

from __future__ import annotations

from urllib.parse import urlparse


def validate_safe_media_url(value: str | None) -> str | None:
    """Accept only ``None``/empty, a same-origin relative path, or a
    fully-qualified ``https://`` URL. Reject every other scheme.

    Every legitimate storage origin in this stack is HTTPS (Supabase
    public buckets) and the in-app image proxy uses same-origin ``/img/``
    paths, so this allows both real shapes while blocking dangerous
    schemes and mixed-content ``http://``.
    """
    if value is None or not value.strip():
        return None
    candidate = value.strip()
    # Same-origin relative path (e.g. the ``/img/`` proxy convention).
    # Reject protocol-relative ``//host`` which is NOT same-origin.
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    parsed = urlparse(candidate)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("must be an https:// URL or a same-origin path")
    return candidate
