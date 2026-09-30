"""UTC is the one truth for every instant a client sends.

A value with no zone is read as UTC by every request model, not only by
course events. Before, a cohort sent one bound with an offset and one
without failed with a 500 (``TypeError`` comparing aware and naive), and a
bare deadline went on to Postgres to be read in the session's zone
(2026-09-30 time audit).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.assignment import AssignmentCreate
from app.schemas.cohort import CohortCreate


def test_a_bare_deadline_is_utc() -> None:
    a = AssignmentCreate(chapter_id="ch-1", title="Эссе", due_date="2026-10-01T23:59:00")
    assert a.due_date == datetime(2026, 10, 1, 23, 59, tzinfo=UTC)


def test_an_offset_is_kept_as_the_instant_it_names() -> None:
    a = AssignmentCreate(chapter_id="ch-1", title="Эссе", due_date="2026-10-01T23:59:00-04:00")
    assert a.due_date is not None
    assert a.due_date.astimezone(UTC) == datetime(2026, 10, 2, 3, 59, tzinfo=UTC)


def test_mixed_cohort_bounds_are_compared_not_crashed_on() -> None:
    ok = CohortCreate(name="Осень", start_date="2026-10-01T00:00:00Z", end_date="2026-12-01T00:00:00")
    assert ok.end_date is not None and ok.end_date.tzinfo is not None
    with pytest.raises(ValidationError):
        CohortCreate(name="Осень", start_date="2026-12-01T00:00:00+00:00", end_date="2026-10-01T00:00:00")
