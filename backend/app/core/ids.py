"""Coercing identifiers before they reach a query.

Half the ids in this codebase travel as strings — path parameters, dictionary
keys, JSON payloads — and the columns they are compared against are UUIDs.
Postgres forgives the mismatch: the driver hands the string over and the server
casts it. SQLite, which the test suite runs on, does not: SQLAlchemy's UUID
binding reaches for ``value.hex`` and an ``AttributeError`` surfaces as a 503.

The two failure modes are the same defect wearing different clothes. Prod keeps
working, so nothing looks wrong; the test that would have caught the *next*
mistake on that route can't run at all, so the route quietly loses its cover.
That has now happened three times in the grading code alone.

Coerce at the boundary — the moment an id enters a filter — and both backends
see the same thing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Iterable


def as_uuid(value: UUID | str | None) -> UUID | None:
    """A ``UUID`` for anything that is one, ``None`` for anything that isn't.

    Deliberately lenient about malformed input: a caller filtering on garbage
    should get an empty result, not a 500. Callers that need to *reject* a bad
    id should validate it themselves — FastAPI's ``student_id: UUID`` parameter
    already does exactly that at the routes.
    """
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def as_uuids(values: Iterable[UUID | str]) -> list[UUID]:
    """The list form, for ``IN`` filters. Unparseable entries are dropped."""
    return [u for u in (as_uuid(v) for v in values) if u is not None]
