# ruff: noqa: RUF001
# The renderings below are Cyrillic prose, one-letter prepositions included.
"""A banner shown to every user was shown in one language.

An announcement with ``course_id IS NULL`` is the admin-authored notice
on every dashboard on the platform. It had no translation path at all,
and each of the three ways in was shut for a different reason:

* the create route reconciles only ``if data.course_id``;
* the registry resolves an announcement's language through its course,
  so ``reconcile_entity`` returns an empty report the moment there
  isn't one;
* ``course_tree`` selects ``Announcement.course_id == course.id``, so no
  course walk ever yields a global row.

And because a reader is never served a language they did not choose, the
result was not "the German sees the Russian original". The German saw
``title=''`` and ``content=''`` — a banner with nothing in it.

These pin the pass that fixes it: the sweep finds a global announcement,
translates it into every other language, does not charge for it twice,
and does not go back for one that only a person can move.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.announcement import Announcement
from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Course, CourseStatus
from app.models.user import User, UserRole
from app.schemas.locale import LOCALE_CODES
from app.services.content_versions.read import fetch_cv_entity_texts_with_fallback
from app.services.content_versions.write import record_human_version
from app.services.translation.protocol import TranslationResult
from app.services.translation.reconciler import sweep_courses, sweep_global_announcements
from app.services.translation.service import reset_translation_provider_cache

from ._fake_translation import fake_translate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.translation.protocol import TranslationRequest

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")

# Real sentences, not a transliteration: the pipeline reads what comes
# back, and a "translation" that is still recognisably Russian lands in
# ``needs_review`` and is never served. A fake that tripped the
# validator would fail these tests for a reason that has nothing to do
# with announcements.
_RENDERINGS: dict[str, dict[str, str]] = {
    "Занятия начинаются в понедельник": {
        "en": "Classes begin on Monday",
        "de": "Der Unterricht beginnt am Montag",
        "uk": "Заняття починаються в понеділок",
    },
    "Первое занятие пройдёт в главном зале.": {
        "en": "The first class will be held in the main hall.",
        "de": "Die erste Stunde findet im großen Saal statt.",
        "uk": "Перше заняття відбудеться у головній залі.",
    },
}


class _Provider:
    name = "recording"

    def __init__(self) -> None:
        self.calls: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls.append(request)
        rendering = _RENDERINGS.get(request.text, {}).get(request.target_locale)
        return TranslationResult(
            text=rendering or fake_translate(request.text, target_locale=request.target_locale),
            model="test",
        )


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


@pytest.fixture
def admin(db: Session) -> User:
    user = User(
        id=ADMIN_ID,
        email="global-banner@example.com",
        full_name="Platform Admin",
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    db.commit()
    return user


def _global_announcement(db: Session, *, author_id: uuid.UUID) -> Announcement:
    """A site-wide announcement as the create route leaves it: no course,
    both texts in ``content_versions`` at the author's language."""
    announcement = Announcement(id=uuid.uuid4(), course_id=None, created_by=author_id)
    db.add(announcement)
    db.flush()
    for field, text in (
        ("title", "Занятия начинаются в понедельник"),
        ("content", "Первое занятие пройдёт в главном зале."),
    ):
        record_human_version(
            db,
            entity_type="announcement",
            entity_id=str(announcement.id),
            field=field,
            locale="ru",
            text=text,
            authored_by=author_id,
        )
    db.commit()
    return announcement


def _reader_sees(db: Session, announcement: Announcement, locale: str) -> dict[str, str | None]:
    """What the banner resolves to for a reader who chose ``locale`` —
    the same call the list route makes, fallback and all."""
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="announcement",
        entity_ids=[str(announcement.id)],
        fields=["title", "content"],
        display_locale=locale,
        source_locale="ru",
    )
    return {field: texts.get((str(announcement.id), field)) for field in ("title", "content")}


class TestTheBannerEverybodySees:
    def test_a_german_reader_gets_more_than_an_empty_banner(self, db: Session, admin: User) -> None:
        announcement = _global_announcement(db, author_id=admin.id)
        assert _reader_sees(db, announcement, "de") == {"title": None, "content": None}, (
            "the fixture should start with nothing for a German reader"
        )

        sweep_global_announcements(db, provider=_Provider())

        seen = _reader_sees(db, announcement, "de")
        assert seen["title"] and seen["title"].strip()
        assert seen["content"] and seen["content"].strip()

    def test_every_served_language_gets_it(self, db: Session, admin: User) -> None:
        announcement = _global_announcement(db, author_id=admin.id)
        sweep_global_announcements(db, provider=_Provider())

        for locale in LOCALE_CODES:
            seen = _reader_sees(db, announcement, locale)
            assert all(text and text.strip() for text in seen.values()), locale

    def test_it_is_not_translated_into_the_language_it_was_written_in(self, db: Session, admin: User) -> None:
        _global_announcement(db, author_id=admin.id)
        provider = _Provider()

        sweep_global_announcements(db, provider=provider)

        assert provider.calls, "nothing was translated at all"
        assert all(call.target_locale != "ru" for call in provider.calls)

    def test_running_it_twice_costs_nothing(self, db: Session, admin: User) -> None:
        _global_announcement(db, author_id=admin.id)
        first = _Provider()
        sweep_global_announcements(db, provider=first)

        second = _Provider()
        sweep_global_announcements(db, provider=second)

        assert first.calls
        assert second.calls == [], "settled text was sent to the provider again"

    def test_a_row_waiting_on_a_person_is_not_asked_again(self, db: Session, admin: User) -> None:
        # Same rule as the course sweep: temperature 0 returns the same
        # verdict, so this moves through the admin surface or not at all.
        announcement = _global_announcement(db, author_id=admin.id)
        sweep_global_announcements(db, provider=_Provider())
        row = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_type == "announcement",
                ContentVersion.entity_id == str(announcement.id),
                ContentVersion.field == "title",
                ContentVersion.locale == "de",
                ContentVersion.superseded_by.is_(None),
            )
            .one()
        )
        row.status = ContentVersionStatus.NEEDS_REVIEW
        db.commit()

        provider = _Provider()
        sweep_global_announcements(db, provider=provider)

        assert provider.calls == []


class TestTheSweepReachesIt:
    def test_an_idle_sweep_translates_the_global_banner(self, db: Session, admin: User) -> None:
        # The worker's only call into the reconciler is ``sweep_courses``.
        # A pass it does not reach is a pass that does not run.
        announcement = _global_announcement(db, author_id=admin.id)

        report = sweep_courses(db, limit=5, provider=_Provider())

        assert report.announcement_rows.translated > 0
        assert all(text for text in _reader_sees(db, announcement, "uk").values())

    def test_it_happens_even_when_there_is_no_course_to_examine(self, db: Session, admin: User) -> None:
        # The sweep used to return the moment its course query came back
        # empty, which on a catalogue-less deployment is every tick.
        announcement = _global_announcement(db, author_id=admin.id)
        assert db.query(Course).count() == 0

        sweep_courses(db, limit=5, provider=_Provider())

        assert all(text for text in _reader_sees(db, announcement, "en").values())

    def test_a_course_announcement_is_left_to_the_course(self, db: Session, admin: User) -> None:
        # This pass is for the rows nothing else can see. A course-bound
        # announcement is walked by ``course_tree`` and translated with
        # its course's language, and picking it up here as well would
        # mean two passes deciding its source direction separately.
        course = Course(
            id=f"course-{uuid.uuid4().hex[:8]}",
            status=CourseStatus.PUBLISHED,
            source_locale="ru",
            created_by=admin.id,
        )
        db.add(course)
        db.flush()
        announcement = Announcement(id=uuid.uuid4(), course_id=course.id, created_by=admin.id)
        db.add(announcement)
        db.flush()
        record_human_version(
            db,
            entity_type="announcement",
            entity_id=str(announcement.id),
            field="title",
            locale="ru",
            text="Занятия начинаются в понедельник",
            authored_by=admin.id,
        )
        db.commit()

        provider = _Provider()
        sweep_global_announcements(db, provider=provider)

        assert provider.calls == []
