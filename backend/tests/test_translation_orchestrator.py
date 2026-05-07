"""Tests for the domain-level translation orchestrator + publish hook.

These tests exercise the orchestrator without going through Gemini: a fake
``TranslationProvider`` is injected so we can assert exactly which calls
are made and how the resulting ``content_translations`` rows look.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.models.content_translation import ContentTranslation
from app.models.course import Course
from app.models.user import User
from app.services.translation.course_pipeline import translate_course_content
from app.services.translation.orchestrator import (
    TranslationFieldSpec,
    other_locales,
    translate_course_metadata,
    translate_entity_fields,
)
from app.services.translation.protocol import (
    TranslationError,
    TranslationRequest,
    TranslationResult,
)
from app.services.translation.service import reset_translation_provider_cache
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Fake provider — captures every call so tests can assert on them.
# ---------------------------------------------------------------------------


class _RecordingProvider:
    name = "recording"

    def __init__(self, *, failures: set[str] | None = None) -> None:
        self.calls: list[TranslationRequest] = []
        self._failures = failures or set()

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls.append(request)
        if request.text in self._failures:
            raise TranslationError(f"forced failure for {request.text!r}")
        # Return a deterministic, distinguishable string per target locale so
        # assertions can pinpoint which row a translation produced.
        return TranslationResult(text=f"[{request.target_locale}]{request.text}", model="test")

    def translate_batch(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        return [self.translate(r) for r in requests]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_teacher(db: Session) -> None:
    """Seed the teacher row required by the ``courses.created_by`` FK.

    The orchestrator unit tests don't use the ``teacher`` fixture (they
    operate on ``db`` directly), so we insert the row on demand. A duplicate
    insert is harmless because we check first.
    """
    if db.get(User, TEACHER_ID) is not None:
        return
    db.add(
        User(
            id=TEACHER_ID,
            email="teacher@example.com",
            full_name="Test Teacher",
            role="teacher",
        )
    )
    db.commit()


def _make_course(db: Session, **overrides: Any) -> Course:
    _ensure_teacher(db)
    defaults = {
        "id": str(uuid.uuid4()),
        "title": "Acts of the Apostles",
        "description": "An overview of the early Church.",
        "status": "draft",
        "source_locale": "ru",
        "created_by": TEACHER_ID,
    }
    defaults.update(overrides)
    course = Course(**defaults)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


# ---------------------------------------------------------------------------
# Pure-helper tests
# ---------------------------------------------------------------------------


def test_other_locales_excludes_source():
    assert other_locales("ru") == ("en",)
    assert other_locales("en") == ("ru",)


# ---------------------------------------------------------------------------
# Orchestrator behaviour
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    """Make the orchestrator believe a provider is configured.

    The default ``GEMINI_API_KEY`` is unset in tests, which would short-circuit
    ``is_translation_enabled`` to ``False`` and skip every call. We patch the
    settings field directly so the orchestrator runs end-to-end.
    """
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        "fake-test-key",
        raising=False,
    )
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def test_translate_course_metadata_writes_rows_for_each_target(db: Session):
    course = _make_course(db)
    provider = _RecordingProvider()

    report = translate_course_metadata(db, course, provider=provider)

    # ru source -> en target x 2 fields (title + description)
    assert report.translated == 2
    assert report.failed == 0

    rows = db.query(ContentTranslation).filter_by(entity_type="course", entity_id=course.id).all()
    assert {(r.field, r.locale) for r in rows} == {("title", "en"), ("description", "en")}
    assert all(r.status == "ok" for r in rows)
    assert all(r.origin == "mt" for r in rows)
    assert all(r.text.startswith("[en]") for r in rows)


def test_translate_course_metadata_skips_unchanged_source(db: Session):
    course = _make_course(db)
    provider = _RecordingProvider()

    translate_course_metadata(db, course, provider=provider)
    first_call_count = len(provider.calls)
    assert first_call_count == 2

    # Re-running with the same source text must short-circuit on source_hash.
    report = translate_course_metadata(db, course, provider=provider)
    assert len(provider.calls) == first_call_count, "provider should not be re-invoked"
    assert report.skipped == 2
    assert report.translated == 0


def test_translate_course_metadata_retranslates_when_source_changes(db: Session):
    course = _make_course(db)
    provider = _RecordingProvider()

    translate_course_metadata(db, course, provider=provider)

    course.title = "Acts of the Apostles — Revised"
    db.commit()

    report = translate_course_metadata(db, course, provider=provider)
    assert report.translated == 1  # only title changed
    assert report.skipped == 1  # description unchanged

    title_row = (
        db.query(ContentTranslation)
        .filter_by(entity_type="course", entity_id=course.id, field="title", locale="en")
        .one()
    )
    assert title_row.text == "[en]Acts of the Apostles — Revised"


def test_translate_course_metadata_preserves_human_translations(db: Session):
    course = _make_course(db)
    provider = _RecordingProvider()

    db.add(
        ContentTranslation(
            entity_type="course",
            entity_id=course.id,
            field="title",
            locale="en",
            text="Hand-crafted English title",
            source_hash="0" * 32,  # intentionally stale
            status="ok",
            origin="human",
        )
    )
    db.commit()

    report = translate_course_metadata(db, course, provider=provider)

    # Title was human-edited so the orchestrator must not touch it; the
    # description still lacks a row, so that one gets created.
    title_row = (
        db.query(ContentTranslation)
        .filter_by(entity_type="course", entity_id=course.id, field="title", locale="en")
        .one()
    )
    assert title_row.origin == "human"
    assert title_row.text == "Hand-crafted English title"
    assert report.skipped >= 1
    assert report.translated == 1  # description


def test_translate_entity_fields_records_failed_rows(db: Session):
    course = _make_course(db)
    provider = _RecordingProvider(failures={course.title or ""})

    report = translate_entity_fields(
        db,
        entity_type="course",
        entity_id=str(course.id),
        source_locale="ru",
        fields=[
            TranslationFieldSpec(field="title", text=course.title, content_kind="title"),
            TranslationFieldSpec(field="description", text=course.description),
        ],
        provider=provider,
    )

    assert report.failed == 1
    assert report.translated == 1

    title_row = (
        db.query(ContentTranslation)
        .filter_by(entity_type="course", entity_id=course.id, field="title", locale="en")
        .one()
    )
    assert title_row.status == "failed"


def test_translate_entity_fields_skips_empty_text(db: Session):
    course = _make_course(db, description=None)
    provider = _RecordingProvider()

    report = translate_entity_fields(
        db,
        entity_type="course",
        entity_id=str(course.id),
        source_locale="ru",
        fields=[
            TranslationFieldSpec(field="title", text=course.title),
            TranslationFieldSpec(field="description", text=None),
        ],
        provider=provider,
    )

    assert report.translated == 1
    # Empty description must NOT have called the provider.
    assert all(req.text != "" for req in provider.calls)
    rows = db.query(ContentTranslation).filter_by(entity_type="course", entity_id=course.id).all()
    assert {r.field for r in rows} == {"title"}


def test_translate_entity_fields_survives_concurrent_insert(monkeypatch, db: Session):
    """Two concurrent translation hooks must not crash the orchestrator.

    Simulates the race where ``_translate_one_field`` selects no existing
    row (peer hasn't committed yet), the peer commits, and our INSERT then
    hits ``content_translations_unique``. The savepoint pattern must catch
    the ``IntegrityError`` and convert the work into an in-place update,
    not propagate the 500.
    """
    course = _make_course(db)

    # Pre-seed the row that "the other concurrent worker" already inserted.
    db.add(
        ContentTranslation(
            entity_type="course",
            entity_id=course.id,
            field="title",
            locale="en",
            text="[en]preexisting",
            source_hash="0" * 64,  # stale hash so the orchestrator wants to update
            status="ok",
            origin="mt",
        )
    )
    db.commit()

    # Make the orchestrator's first SELECT return None so it takes the
    # "INSERT new row" branch — exactly the race window we worry about in
    # production. Subsequent queries (notably the savepoint-recovery refetch)
    # see the real data.
    seen = {"calls": 0}
    original_query = db.query

    def patched_query(model, *args, **kwargs):
        q = original_query(model, *args, **kwargs)
        if model is ContentTranslation and seen["calls"] == 0:
            seen["calls"] += 1
            q.one_or_none = lambda: None  # type: ignore[method-assign]
        return q

    monkeypatch.setattr(db, "query", patched_query)
    provider = _RecordingProvider()

    report = translate_entity_fields(
        db,
        entity_type="course",
        entity_id=str(course.id),
        source_locale="ru",
        fields=[TranslationFieldSpec(field="title", text=course.title)],
        provider=provider,
    )

    # The orchestrator must survive — exactly one translation, no failure.
    assert report.failed == 0
    assert report.translated == 1

    # Restore real query so the assertion below uses an unpatched session.
    monkeypatch.setattr(db, "query", original_query)
    rows = (
        db.query(ContentTranslation)
        .filter_by(entity_type="course", entity_id=course.id, field="title", locale="en")
        .all()
    )
    # The unique constraint stays intact: still exactly one row.
    assert len(rows) == 1
    # And it carries the freshly translated text, not the pre-seeded value.
    assert rows[0].text.startswith("[en]")
    assert rows[0].text != "[en]preexisting"


def test_translate_entity_fields_no_op_when_provider_disabled(monkeypatch, db: Session):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        None,
        raising=False,
    )
    reset_translation_provider_cache()

    course = _make_course(db)
    report = translate_course_metadata(db, course)

    assert (report.translated, report.skipped, report.failed) == (0, 0, 0)
    assert db.query(ContentTranslation).count() == 0


# ---------------------------------------------------------------------------
# HTTP-level integration: publish hook + manual trigger endpoint
# ---------------------------------------------------------------------------


def _patch_provider(monkeypatch, provider: _RecordingProvider) -> None:
    def _wrapped(db, course):
        return translate_course_content(db, course, provider=provider)

    monkeypatch.setattr(
        "app.api.v1.courses.crud.translate_course_content",
        _wrapped,
    )
    monkeypatch.setattr(
        "app.api.v1.courses.translate.translate_course_content",
        _wrapped,
    )


def test_publishing_a_course_triggers_translation(monkeypatch, client: TestClient):
    provider = _RecordingProvider()
    _patch_provider(monkeypatch, provider)

    course = client.post(
        "/api/v1/courses",
        json={"title": "Genesis Overview", "description": "Intro to Genesis."},
    ).json()

    assert provider.calls == [], "draft create must not translate"

    resp = client.put(f"/api/v1/courses/{course['id']}", json={"status": "published"})
    assert resp.status_code == 200
    assert len(provider.calls) == 2  # title + description


def test_publishing_does_not_translate_again_on_idempotent_update(monkeypatch, client: TestClient):
    provider = _RecordingProvider()
    _patch_provider(monkeypatch, provider)

    course = client.post(
        "/api/v1/courses",
        json={"title": "Acts", "description": "Course."},
    ).json()

    client.put(f"/api/v1/courses/{course['id']}", json={"status": "published"})
    assert len(provider.calls) == 2

    # Publishing-while-already-published must not re-trigger the hook.
    client.put(f"/api/v1/courses/{course['id']}", json={"status": "published"})
    assert len(provider.calls) == 2


def test_publish_hook_swallows_translation_failures(monkeypatch, client: TestClient):
    """A Gemini outage must not block ``draft → published``."""

    def _boom(_db, _course):
        raise RuntimeError("simulated translation outage")

    monkeypatch.setattr("app.api.v1.courses.crud.translate_course_content", _boom)
    monkeypatch.setattr("app.api.v1.courses.translate.translate_course_content", _boom)

    course = client.post("/api/v1/courses", json={"title": "Genesis"}).json()
    resp = client.put(f"/api/v1/courses/{course['id']}", json={"status": "published"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "published"


def test_manual_translate_endpoint_backfills_existing_courses(monkeypatch, client: TestClient):
    provider = _RecordingProvider()
    _patch_provider(monkeypatch, provider)

    course = client.post(
        "/api/v1/courses",
        json={"title": "Acts", "description": "Course on Acts."},
    ).json()

    # Publish *without* the hook running so we end up in the "already
    # published, no translations yet" state that prod is in for legacy
    # courses.
    monkeypatch.setattr(
        "app.api.v1.courses.crud.translate_course_content",
        lambda db, course: None,
    )
    client.put(f"/api/v1/courses/{course['id']}", json={"status": "published"})
    assert provider.calls == []

    # Now restore the patched orchestrator and call the manual endpoint.
    _patch_provider(monkeypatch, provider)
    resp = client.post(f"/api/v1/courses/{course['id']}/translate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is True
    assert body["translated"] == 2
    assert body["failed"] == 0


def test_manual_translate_endpoint_returns_disabled_when_provider_off(monkeypatch, client: TestClient):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.courses.translate.is_translation_enabled",
        lambda: False,
    )

    course = client.post("/api/v1/courses", json={"title": "Acts"}).json()

    resp = client.post(f"/api/v1/courses/{course['id']}/translate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["translated"] == 0
