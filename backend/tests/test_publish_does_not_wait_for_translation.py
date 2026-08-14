"""Saving a course does not wait for it to be translated.

The publish path used to call ``translate_course_content`` directly
from inside the request handler. On a course of any size that is a
Gemini round-trip per field, in series, while the teacher's browser
waits — and past 300 seconds Vercel answers 504 to a teacher whose
save had in fact succeeded. Production hit exactly that.

The second half of the bug: with ``TRANSLATION_QUEUE_ENABLED`` on,
the entity hooks were *already* enqueueing the same work, so the
synchronous call in the request was buying nothing but latency.

These tests pin the endpoint's behaviour against the queue setting —
one job enqueued, no provider call in the request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.models.translation_job import TranslationJob, TranslationJobStatus

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


@pytest.fixture
def queue_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.translation.pipeline_hooks.settings.TRANSLATION_QUEUE_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.translation.pipeline_hooks.is_translation_enabled",
        lambda: True,
    )


def _create_draft(client: TestClient) -> str:
    course = client.post(
        "/api/v1/courses",
        json={"title": "Genesis Overview", "description": "Intro to Genesis."},
    ).json()
    return str(course["id"])


class TestPublishingEnqueuesInsteadOfWaiting:
    def test_publish_enqueues_one_job(self, client: TestClient, db: Session, queue_mode):
        course_id = _create_draft(client)

        response = client.put(f"/api/v1/courses/{course_id}", json={"status": "published"})
        assert response.status_code == 200

        jobs = db.query(TranslationJob).filter_by(course_id=course_id).all()
        assert len(jobs) == 1
        assert jobs[0].status == TranslationJobStatus.QUEUED

    def test_publish_does_not_call_the_provider_in_the_request(
        self,
        client: TestClient,
        db: Session,
        queue_mode,
        monkeypatch: pytest.MonkeyPatch,
    ):
        calls: list[object] = []

        def _should_not_run(*args, **kwargs):
            calls.append(args)
            raise AssertionError("the request must not translate; the worker does")

        monkeypatch.setattr(
            "app.services.translation.pipeline_hooks.translate_course_content",
            _should_not_run,
        )
        course_id = _create_draft(client)

        response = client.put(f"/api/v1/courses/{course_id}", json={"status": "published"})
        assert response.status_code == 200
        assert calls == []

    def test_repeated_saves_do_not_pile_up_jobs(self, client: TestClient, db: Session, queue_mode):
        course_id = _create_draft(client)
        client.put(f"/api/v1/courses/{course_id}", json={"status": "published"})

        for suffix in ("one", "two", "three"):
            client.put(f"/api/v1/courses/{course_id}", json={"description": f"Intro {suffix}."})

        jobs = db.query(TranslationJob).filter_by(course_id=course_id).all()
        assert len(jobs) == 1, "a teacher mashing Save must not multiply the worker's work"


class TestDraftsAreStillNotTranslated:
    def test_saving_a_draft_enqueues_nothing(self, client: TestClient, db: Session, queue_mode):
        course_id = _create_draft(client)

        client.put(f"/api/v1/courses/{course_id}", json={"description": "Still drafting."})

        assert db.query(TranslationJob).filter_by(course_id=course_id).count() == 0
