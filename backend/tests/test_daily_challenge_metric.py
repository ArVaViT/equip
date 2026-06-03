"""Tests for ``equip.daily_challenge.attempt_total`` emission from
``submit_attempt``.

The metric drives the Course Engagement dashboard's daily-challenge
participation tile. Pinned guarantees:

* Fires once per *new* attempt (``is_new_attempt=True``).
* Idempotent re-submits (same user, same day) return 201 but do
  NOT increment — otherwise a double-click would inflate the
  "unique participants" denominator and skew correct-rate math.
* Tagged with ``challenge_date`` (so the dashboard can plot by day)
  and ``is_correct`` (so correct-rate is derivable from a single
  metric, no second counter needed).
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.models.daily_challenge import DailyChallengeOption
from app.models.user import User, UserRole

# Reuse the proven seed helpers from the existing DC test file. They
# build a question + 4 options + content_versions text rows the way
# the editorial pipeline will when it lands; matching that shape
# means this test exercises the real submit path, not a synthetic one.
from .test_daily_challenge_service import _schedule_for_today, _seed_question_with_options

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session

    from app.models.daily_challenge import DailyChallengeQuestion


def _seed_dc_today(db: Session) -> tuple[DailyChallengeQuestion, uuid.UUID, uuid.UUID]:
    """Returns (question, correct_option_id, wrong_option_id)."""
    author = User(
        id=uuid.uuid4(),
        email=f"a-{uuid.uuid4().hex[:8]}@e.com",
        full_name="A",
        role=UserRole.TEACHER.value,
    )
    db.add(author)
    db.commit()
    q = _seed_question_with_options(db, author_id=author.id)
    _schedule_for_today(db, q, scheduled_by=author.id)
    db.refresh(q)
    correct = next(o.id for o in db.query(DailyChallengeOption).filter(DailyChallengeOption.question_id == q.id).all() if o.is_correct)
    wrong = next(o.id for o in db.query(DailyChallengeOption).filter(DailyChallengeOption.question_id == q.id).all() if not o.is_correct)
    return q, correct, wrong


class TestAttemptMetric:
    def test_correct_attempt_emits_with_is_correct_true(
        self,
        db: Session,
        student_client,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _, correct_id, _ = _seed_dc_today(db)

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            resp = student_client.post(
                "/api/v1/daily-challenge/today/attempt",
                json={"selected_option_id": str(correct_id)},
            )
        assert resp.status_code == 201, resp.text
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.daily_challenge.attempt_total" in m]
        assert events, "expected attempt_total event"
        assert any("is_correct=true" in m for m in events)
        assert any("value=1.0" in m for m in events)

    def test_incorrect_attempt_emits_with_is_correct_false(
        self,
        db: Session,
        student_client,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _, _, wrong_id = _seed_dc_today(db)

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            resp = student_client.post(
                "/api/v1/daily-challenge/today/attempt",
                json={"selected_option_id": str(wrong_id)},
            )
        assert resp.status_code == 201
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.daily_challenge.attempt_total" in m]
        assert events
        assert any("is_correct=false" in m for m in events)

    def test_idempotent_resubmit_does_not_re_emit(
        self,
        db: Session,
        student_client,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Same user, same option, second POST — returns 201 (same
        attempt) but MUST NOT re-fire the counter."""
        _, correct_id, _ = _seed_dc_today(db)

        student_client.post(
            "/api/v1/daily-challenge/today/attempt",
            json={"selected_option_id": str(correct_id)},
        )
        caplog.clear()

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            resp = student_client.post(
                "/api/v1/daily-challenge/today/attempt",
                json={"selected_option_id": str(correct_id)},
            )
        assert resp.status_code == 201
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.daily_challenge.attempt_total" in m]
        assert events == [], "idempotent re-submit must NOT re-emit"
