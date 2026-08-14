"""Phase 1g tests: MT pipeline dual-writes into ``content_versions``.

Pins behaviour for the orchestrator's shadow writes:

* Every successful MT row that gets written to ``content_translations``
  also appears as an active ``content_versions`` row with
  ``origin='mt'`` and the matching ``source_locale`` / ``source_hash``.
* Every MT failure gets shadowed via ``record_mt_failure`` so the
  retry queue has a single source of truth in content_versions.
* When the human source row exists in content_versions, the MT
  row's ``source_version_id`` points at it. When it doesn't (mid-
  rollout / unbackfilled legacy data), the MT row is still
  recorded — ``source_version_id`` is just ``NULL``.
* The orchestrator's existing idempotency short-circuit (matching
  source_hash, status=ok) skips BOTH stores in lockstep so no
  duplicate content_versions rows are created on a no-op pass.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion
from app.models.course import Course
from app.models.user import User
from app.services.content_versions import record_human_version
from app.services.translation.orchestrator import (
    TranslationFieldSpec,
    translate_entity_fields,
)
from app.services.translation.protocol import (
    TranslationError,
    TranslationRequest,
    TranslationResult,
)
from app.services.translation.service import reset_translation_provider_cache
from tests._fake_translation import fake_translate
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class _RecordingProvider:
    name = "recording"

    def __init__(self, *, failures: set[str] | None = None) -> None:
        self.calls: list[TranslationRequest] = []
        self._failures = failures or set()

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls.append(request)
        if request.text in self._failures:
            raise TranslationError(f"forced failure for {request.text!r}")
        return TranslationResult(
            text=fake_translate(request.text, target_locale=request.target_locale),
            model="test",
        )


@pytest.fixture(autouse=True)
def _enable_provider(monkeypatch: pytest.MonkeyPatch):
    """The orchestrator early-exits when no provider is configured —
    set a fake API key so ``is_translation_enabled`` returns True
    and reset the cached provider on tear-down."""
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("test-key"),
        raising=False,
    )
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def _seed_teacher(db: Session) -> None:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="t@example.com", full_name="T", role="teacher"))
        db.commit()


def _make_course(db: Session, *, source_locale: str = "en") -> Course:
    _seed_teacher(db)
    course = Course(
        id=str(uuid.uuid4()),
        title="Source Title",
        description="Source Description.",
        created_by=TEACHER_ID,
        status="published",
        source_locale=source_locale,
    )
    db.add(course)
    db.commit()
    return course


def _active(db: Session, *, entity_type: str, entity_id: str, locale: str) -> ContentVersion | None:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.locale == locale,
            ContentVersion.superseded_by.is_(None),
        )
        .one_or_none()
    )


class TestSuccessDualWrite:
    def test_successful_mt_writes_content_versions_row(self, db: Session):
        course = _make_course(db)
        provider = _RecordingProvider()
        translate_entity_fields(
            db,
            entity_type="course",
            entity_id=str(course.id),
            source_locale="en",
            fields=[TranslationFieldSpec(field="title", text="Hello", content_kind="title")],
            provider=provider,
        )
        cv = _active(db, entity_type="course", entity_id=str(course.id), locale="ru")
        assert cv is not None
        assert cv.origin == "mt"
        assert cv.status == "ok"
        assert cv.text == "[ru]Хелло"
        assert cv.source_locale == "en"
        assert cv.source_hash  # source_hash populated from compute_source_hash

    def test_mt_links_to_source_version_when_present(self, db: Session):
        course = _make_course(db)
        # Pre-seed an active human source version in content_versions.
        source_row = record_human_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale="en",
            text="Hello",
        )
        db.commit()
        provider = _RecordingProvider()
        translate_entity_fields(
            db,
            entity_type="course",
            entity_id=str(course.id),
            source_locale="en",
            fields=[TranslationFieldSpec(field="title", text="Hello", content_kind="title")],
            provider=provider,
        )
        cv = _active(db, entity_type="course", entity_id=str(course.id), locale="ru")
        assert cv is not None
        assert cv.source_version_id == source_row.id

    def test_mt_records_without_source_version_when_absent(self, db: Session):
        # No pre-existing human source row in content_versions yet —
        # mid-rollout / un-backfilled state. MT row still recorded;
        # source_version_id stays NULL until backfill (Phase 3) lands.
        course = _make_course(db)
        provider = _RecordingProvider()
        translate_entity_fields(
            db,
            entity_type="course",
            entity_id=str(course.id),
            source_locale="en",
            fields=[TranslationFieldSpec(field="title", text="Hello", content_kind="title")],
            provider=provider,
        )
        cv = _active(db, entity_type="course", entity_id=str(course.id), locale="ru")
        assert cv is not None
        assert cv.source_version_id is None

    def test_idempotent_pass_does_not_duplicate_content_versions(self, db: Session):
        course = _make_course(db)
        provider = _RecordingProvider()
        for _ in range(2):
            translate_entity_fields(
                db,
                entity_type="course",
                entity_id=str(course.id),
                source_locale="en",
                fields=[TranslationFieldSpec(field="title", text="Hello", content_kind="title")],
                provider=provider,
            )
        rows = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_type == "course",
                ContentVersion.entity_id == str(course.id),
                ContentVersion.locale == "ru",
            )
            .all()
        )
        assert len(rows) == 1


class TestFailureDualWrite:
    def test_mt_failure_shadowed_as_failed_in_content_versions(self, db: Session):
        course = _make_course(db)
        provider = _RecordingProvider(failures={"Hello"})
        translate_entity_fields(
            db,
            entity_type="course",
            entity_id=str(course.id),
            source_locale="en",
            fields=[TranslationFieldSpec(field="title", text="Hello", content_kind="title")],
            provider=provider,
        )
        cv = _active(db, entity_type="course", entity_id=str(course.id), locale="ru")
        assert cv is not None
        assert cv.status == "failed"
        assert cv.attempts == 1
        assert cv.origin == "mt"
        assert cv.source_locale == "en"

    def test_repeat_failure_bumps_attempts_in_place(self, db: Session):
        course = _make_course(db)
        provider = _RecordingProvider(failures={"Hello"})
        for _ in range(3):
            translate_entity_fields(
                db,
                entity_type="course",
                entity_id=str(course.id),
                source_locale="en",
                fields=[TranslationFieldSpec(field="title", text="Hello", content_kind="title")],
                provider=provider,
            )
        rows = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_type == "course",
                ContentVersion.entity_id == str(course.id),
                ContentVersion.locale == "ru",
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].attempts == 3
        assert rows[0].status == "failed"
