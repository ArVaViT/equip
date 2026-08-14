"""A translation that comes back wrong is parked, not served.

``status='ok'`` used to mean "the HTTP call did not raise". These
tests pin the third state that replaces that meaning: when the
provider answers but the answer fails the structural check
(``services/translation/validation.py``), the row is written with its
text and ``status='needs_review'``.

Two properties matter, and they pull against each other:

* The text is **kept**. Whoever reviews it has to see what the model
  actually said; throwing it away turns a reviewable defect into a
  mystery.
* The row is **not served**. Readers filter on ``ok``, so a parked row
  reads as "not translated yet" rather than being shown to a student
  who chose that language.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Course
from app.models.user import User
from app.services.content_versions.read import fetch_cv_text_bulk
from app.services.translation.orchestrator import (
    TranslationFieldSpec,
    translate_entity_fields,
)
from app.services.translation.protocol import TranslationRequest, TranslationResult
from app.services.translation.service import reset_translation_provider_cache
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RU_SOURCE = "Апостол Павел написал это послание церкви в Коринфе около 55 года."
GOOD_EN = "The apostle Paul wrote this letter to the church in Corinth around the year 55."


@pytest.fixture(autouse=True)
def _translation_enabled(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr("test-key"), raising=False)
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


class _FixedProvider:
    """Returns one prepared answer, whatever it is asked."""

    name = "fixed"

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(text=self.answer, model="test")


def _seed_teacher(db: Session) -> None:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", role="teacher"))
        db.commit()


def _make_course(db: Session) -> Course:
    _seed_teacher(db)
    course = Course(
        id=str(uuid.uuid4()),
        title="Source Title",
        description="Source Description.",
        created_by=TEACHER_ID,
        status="published",
        source_locale="ru",
    )
    db.add(course)
    db.commit()
    return course


def _translate(db: Session, course: Course, answer: str) -> None:
    translate_entity_fields(
        db,
        entity_type="course",
        entity_id=str(course.id),
        source_locale="ru",
        fields=[TranslationFieldSpec(field="description", text=RU_SOURCE, content_kind="plain")],
        target_locales=("en",),
        provider=_FixedProvider(answer),
    )


def _row(db: Session, course: Course) -> ContentVersion | None:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id == str(course.id),
            ContentVersion.locale == "en",
            ContentVersion.superseded_by.is_(None),
        )
        .one_or_none()
    )


class TestAGoodTranslationIsUnaffected:
    def test_clean_answer_is_ok_and_servable(self, db: Session):
        course = _make_course(db)
        _translate(db, course, GOOD_EN)

        row = _row(db, course)
        assert row is not None
        assert row.status == ContentVersionStatus.OK
        assert row.review_reason is None
        assert row.text == GOOD_EN

    def test_report_counts_it_as_translated(self, db: Session):
        course = _make_course(db)
        report = translate_entity_fields(
            db,
            entity_type="course",
            entity_id=str(course.id),
            source_locale="ru",
            fields=[TranslationFieldSpec(field="description", text=RU_SOURCE)],
            target_locales=("en",),
            provider=_FixedProvider(GOOD_EN),
        )
        assert (report.translated, report.needs_review) == (1, 0)


class TestABadTranslationIsParked:
    def test_wrong_language_is_parked_with_its_text(self, db: Session):
        course = _make_course(db)
        # The model answered in the source language.
        _translate(db, course, RU_SOURCE)

        row = _row(db, course)
        assert row is not None
        assert row.status == ContentVersionStatus.NEEDS_REVIEW
        # The text is kept — a reviewer has to see what came back.
        assert row.text == RU_SOURCE
        assert row.review_reason
        assert "not_translated" in row.review_reason or "wrong_language" in row.review_reason

    def test_parked_row_is_not_served_to_readers(self, db: Session):
        course = _make_course(db)
        _translate(db, course, RU_SOURCE)

        served = fetch_cv_text_bulk(
            db,
            [("course", str(course.id), "description")],
            "en",
        )
        # Reads as "not translated yet", not as a translation.
        assert served == {}

    def test_report_counts_it_apart_from_failures(self, db: Session):
        course = _make_course(db)
        report = translate_entity_fields(
            db,
            entity_type="course",
            entity_id=str(course.id),
            source_locale="ru",
            fields=[TranslationFieldSpec(field="description", text=RU_SOURCE)],
            target_locales=("en",),
            provider=_FixedProvider(RU_SOURCE),
        )
        # A failure is retried; a review is read. Different work.
        assert (report.translated, report.failed, report.needs_review) == (0, 0, 1)

    def test_truncated_answer_is_parked(self, db: Session):
        course = _make_course(db)
        _translate(db, course, "The apostle Paul wrote")

        row = _row(db, course)
        assert row is not None
        assert row.status == ContentVersionStatus.NEEDS_REVIEW
        assert "length_suspicious" in (row.review_reason or "")


class TestParkedRowsDoNotChurn:
    def test_unchanged_source_is_not_re_asked(self, db: Session):
        course = _make_course(db)
        _translate(db, course, RU_SOURCE)

        class _Counting(_FixedProvider):
            def __init__(self, answer: str) -> None:
                super().__init__(answer)
                self.calls = 0

            def translate(self, request: TranslationRequest) -> TranslationResult:
                self.calls += 1
                return super().translate(request)

        provider = _Counting(RU_SOURCE)
        report = translate_entity_fields(
            db,
            entity_type="course",
            entity_id=str(course.id),
            source_locale="ru",
            fields=[TranslationFieldSpec(field="description", text=RU_SOURCE)],
            target_locales=("en",),
            provider=provider,
        )
        # Gemini runs at temperature=0: the same source gives the same
        # answer and the same verdict. Re-asking on every save would
        # burn quota to arrive back where we are.
        assert provider.calls == 0
        assert report.skipped == 1

    def test_a_changed_source_gets_another_attempt(self, db: Session):
        course = _make_course(db)
        _translate(db, course, RU_SOURCE)

        # Source edited → different hash → the pipeline asks again,
        # and a good answer promotes the row to ok.
        translate_entity_fields(
            db,
            entity_type="course",
            entity_id=str(course.id),
            source_locale="ru",
            fields=[
                TranslationFieldSpec(
                    field="description",
                    text=RU_SOURCE + " Он писал из Ефеса.",
                )
            ],
            target_locales=("en",),
            provider=_FixedProvider(GOOD_EN + " He wrote from Ephesus."),
        )

        row = _row(db, course)
        assert row is not None
        assert row.status == ContentVersionStatus.OK
        assert row.review_reason is None
