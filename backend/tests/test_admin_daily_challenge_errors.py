"""Error-path tests for ``app.api.v1.admin_daily_challenge``.

The existing editorial / orchestrator tests cover the happy paths.
This file targets the ``except`` branches the existing flow doesn't
trigger — 404 for unknown question, 400 / 409 mappings from the
service-layer ``ValueError`` / ``QuestionRejectedError`` /
``StatusTransitionError`` / ``NotPublishableError``, and the 503 on
``generate`` when the deployment is missing the Gemini key.

The service layer is monkeypatched per-test so the API mapping is the
sole subject under test.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.services.daily_challenge import admin as dc_admin

if TYPE_CHECKING:
    import pytest
    from fastapi.testclient import TestClient


class TestQuestionOr404:
    def test_get_unknown_question_returns_404(self, client: TestClient) -> None:
        """`GET /admin/dc/questions/{uuid}` returns 404 with the
        canonical message when the id doesn't exist. Pin both the
        status code and the message shape since the frontend surfaces
        a localized banner keyed on `RESOURCE_NOT_FOUND`."""
        r = client.get(f"/api/v1/admin/daily-challenge/questions/{uuid.uuid4()}")
        assert r.status_code == 404
        body = r.json()
        assert "not found" in body["detail"]["message"].lower()


class TestCreateQuestionRoute:
    def test_value_error_maps_to_400(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The service raises ``ValueError`` for option-validation
        failures (wrong number of correct options, too few options,
        true/false with wrong arity). The route MUST map it to 400 with
        the validator message intact so the editor can surface it
        inline."""

        def fake_create(*_args: object, **_kwargs: object) -> object:
            raise ValueError("daily challenge question needs at least two options")

        # The route imports ``create_question`` from the admin service
        # at module scope — monkeypatch on the api module's symbol.
        from app.api.v1 import admin_daily_challenge as route_mod

        monkeypatch.setattr(route_mod, "create_question", fake_create)

        r = client.post(
            "/api/v1/admin/daily-challenge/questions",
            json={
                "question_type": "multiple_choice",
                "bible_book": "Romans",
                "bible_chapter": 8,
                "bible_verse_from": 28,
                "question_text": "Test?",
                "options": [
                    {"text": "A", "is_correct": True},
                    {"text": "B", "is_correct": False},
                ],
                "explanation": "x",
            },
        )
        assert r.status_code == 400
        assert "at least two" in r.json()["detail"]["message"]


class TestPromoteQuestion:
    def test_rejected_question_returns_409(
        self,
        client: TestClient,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Trying to promote a question that's been ``rejected=True``
        is a 409 — the editor needs to un-reject before advancing."""
        from app.api.v1 import admin_daily_challenge as route_mod

        # Pre-seed a question row that ``_question_or_404`` will find.
        qid = _seed_minimal_question(db)

        def fake_promote(*_args: object, **_kwargs: object) -> object:
            raise dc_admin.QuestionRejectedError(f"question {qid} is rejected; cannot promote")

        monkeypatch.setattr(route_mod, "promote_status", fake_promote)
        r = client.post(f"/api/v1/admin/daily-challenge/questions/{qid}/promote")
        assert r.status_code == 409
        assert "rejected" in r.json()["detail"]["message"]

    def test_transition_error_returns_409_with_current_status(
        self,
        client: TestClient,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No-forward-edge transition (already at ``published``, etc.)
        is 409 with ``current_status`` in the context — the editor
        renders the current state so the user can correct course."""
        from app.api.v1 import admin_daily_challenge as route_mod

        qid = _seed_minimal_question(db)

        def fake_promote(*_args: object, **_kwargs: object) -> object:
            raise dc_admin.StatusTransitionError("no forward edge from published")

        monkeypatch.setattr(route_mod, "promote_status", fake_promote)
        r = client.post(f"/api/v1/admin/daily-challenge/questions/{qid}/promote")
        assert r.status_code == 409
        body = r.json()["detail"]
        assert "no forward edge" in body["message"]
        assert "current_status" in body["context"]


class TestPublishQuestion:
    def test_rejected_blocks_publish(
        self,
        client: TestClient,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.api.v1 import admin_daily_challenge as route_mod

        qid = _seed_minimal_question(db)

        def fake_publish(*_args: object, **_kwargs: object) -> object:
            raise dc_admin.QuestionRejectedError(f"question {qid} is rejected")

        monkeypatch.setattr(route_mod, "publish_question", fake_publish)
        r = client.post(f"/api/v1/admin/daily-challenge/questions/{qid}/publish")
        assert r.status_code == 409

    def test_transition_error_on_publish_returns_409(
        self,
        client: TestClient,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.api.v1 import admin_daily_challenge as route_mod

        qid = _seed_minimal_question(db)

        def fake_publish(*_args: object, **_kwargs: object) -> object:
            raise dc_admin.StatusTransitionError("cannot publish from draft")

        monkeypatch.setattr(route_mod, "publish_question", fake_publish)
        r = client.post(f"/api/v1/admin/daily-challenge/questions/{qid}/publish")
        assert r.status_code == 409


class TestScheduleRoute:
    def test_question_rejected_returns_409(
        self,
        client: TestClient,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.api.v1 import admin_daily_challenge as route_mod

        qid = _seed_minimal_question(db)

        def fake_schedule(*_args: object, **_kwargs: object) -> object:
            raise dc_admin.QuestionRejectedError("cannot schedule a rejected question")

        monkeypatch.setattr(route_mod, "schedule_for_date", fake_schedule)
        r = client.post(
            "/api/v1/admin/daily-challenge/schedule",
            json={"question_id": str(qid), "challenge_date": "2026-12-31"},
        )
        assert r.status_code == 409

    def test_not_publishable_returns_409_with_date_context(
        self,
        client: TestClient,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.api.v1 import admin_daily_challenge as route_mod

        qid = _seed_minimal_question(db)

        def fake_schedule(*_args: object, **_kwargs: object) -> object:
            raise dc_admin.NotPublishableError("question is not in 'published' status")

        monkeypatch.setattr(route_mod, "schedule_for_date", fake_schedule)
        r = client.post(
            "/api/v1/admin/daily-challenge/schedule",
            json={"question_id": str(qid), "challenge_date": "2026-12-31"},
        )
        assert r.status_code == 409
        body = r.json()["detail"]
        # ``challenge_date`` must be in the context so the operator can
        # see which slot collided.
        assert "challenge_date" in body["context"]


class TestGenerateRoute:
    def test_missing_gemini_key_returns_503(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without a configured Gemini key the route refuses with 503 —
        the editor surfaces an admin-action banner. Pin so a future
        config refactor doesn't accidentally let it 500 instead."""
        from app.core import config as core_config

        monkeypatch.setattr(core_config.settings, "GEMINI_API_KEY", None)

        r = client.post(
            "/api/v1/admin/daily-challenge/generate",
            json={
                "bible_book": "Romans",
                "bible_chapter": 8,
                "bible_verse_from": 28,
                "n_candidates_per_agent": 1,
                "max_survivors": 1,
            },
        )
        assert r.status_code == 503
        assert "GEMINI_API_KEY" in r.json()["detail"]["message"]


# ---------------------------------------------------------------------------
# Local helpers — minimal question row that ``_question_or_404`` will find.
# ---------------------------------------------------------------------------


def _seed_minimal_question(db) -> uuid.UUID:
    """Insert a minimal DailyChallengeQuestion that satisfies the
    ``_question_or_404`` lookup but doesn't need any cv rows — the
    route-level error-mapping tests monkeypatch the service so it
    never reads the question's content.
    """
    from app.models.daily_challenge import DailyChallengeQuestion

    qid = uuid.uuid4()
    q = DailyChallengeQuestion(
        id=qid,
        question_type="multiple_choice",
        status="draft",
        rejected=False,
        bible_book="rom",
        bible_chapter=8,
        bible_verse_from=28,
        source_locale="en",
    )
    db.add(q)
    db.commit()
    return qid
