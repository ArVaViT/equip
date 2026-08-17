# ruff: noqa: RUF001
# The test texts are Russian on purpose: this is about a Russian course
# being read in four languages, and a transliterated stand-in would not
# exercise the language detector the staging path runs on every edit.
"""An edit to a live course lands in every language at once, or in none.

The behaviour under test, stated as a story: a Russian teacher fixes a
sentence in a course that German, Ukrainian and English students are
reading right now. Until this existed, the Russian group saw the fix
immediately and the other three kept reading the translation of the
sentence it replaced — for as long as the queue took. If the edit was
to a quiz question, the four groups were being graded on questions that
no longer said the same thing.

Now the edit waits. Not in ``content_versions`` — no reader's query can
reach it at all — and when the last language is in and checked, all
four change together.

The tests are grouped by the thing that can go wrong:

1. The reader is not shown the edit early.
2. The author is not shown their own edit late.
3. A second edit cannot ride out on the first one's translations.
4. Nothing is staged where there is nobody to protect.
5. An edit that cannot complete says so instead of vanishing.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Course, CourseStatus
from app.models.staged_content_version import StagedContentVersion
from app.models.user import User
from app.services.content_versions.read import fetch_cv_entity_texts_with_fallback
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.staged_edits import (
    author_text,
    promote_ready_fields,
    promote_staged_entity_unconditionally,
    stage_human_edit,
    staged_status_for_course,
)
from app.services.translation.hash import compute_source_hash
from app.services.translation.service import reset_translation_provider_cache
from app.services.translation.staged_pipeline import translate_staged_edits
from tests._fake_translation import fake_translate
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.translation.protocol import TranslationRequest, TranslationResult

_LOCALES = ("ru", "en", "de", "uk")


class _Provider:
    name = "recording"

    def __init__(self) -> None:
        self.calls: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> TranslationResult:
        from app.services.translation.protocol import TranslationResult as Result

        self.calls.append(request)
        return Result(text=fake_translate(request.text, target_locale=request.target_locale), model="test")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


def _ensure_teacher(db: Session) -> None:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", full_name="T", role="teacher"))
        db.commit()


def _published_course(db: Session, **overrides: Any) -> Course:
    """A course being read in four languages: one human source row and a
    translation of it in each of the others."""
    _ensure_teacher(db)
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=overrides.pop("status", CourseStatus.PUBLISHED),
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()

    source_text = "Первое послание к Коринфянам"
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="ru",
        text=source_text,
    )
    source_hash = compute_source_hash(source_text, locale="ru")
    for locale in _LOCALES:
        if locale == "ru":
            continue
        record_mt_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale=locale,
            text=f"[{locale}] First Corinthians",
            source_locale="ru",
            source_hash=source_hash,
        )
    db.commit()
    return course


def _served_text(db: Session, course: Course, locale: str) -> str | None:
    """What a reader in ``locale`` is actually given."""
    resolved = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course",
        entity_ids=[str(course.id)],
        fields=["title"],
        display_locale=locale,
        source_locale="ru",
        fallback="none",
    )
    return resolved.get((str(course.id), "title"))


def _edit(db: Session, course: Course, text: str) -> None:
    stage_human_edit(
        db,
        entity_type="course",
        entity_id=str(course.id),
        course_id=str(course.id),
        field="title",
        locale="ru",
        text=text,
    )
    db.commit()


# ---------------------------------------------------------------------------
# 1. The reader is not shown the edit early
# ---------------------------------------------------------------------------


def test_readers_keep_the_previous_version_while_the_edit_translates(db: Session):
    """Including readers of the language it was written in. That is the
    part the old behaviour got wrong: the Russian group jumped ahead of
    everybody else."""
    course = _published_course(db)
    _edit(db, course, "Первое послание апостола Павла к Коринфянам")

    for locale in _LOCALES:
        served = _served_text(db, course, locale)
        assert served is not None
        assert "апостола Павла" not in (served or "")


def test_the_edit_is_not_in_the_table_readers_query(db: Session):
    """The structural guarantee behind the one above: an unreleased edit
    is not one predicate away from being served, it is in a different
    table entirely."""
    course = _published_course(db)
    _edit(db, course, "Совершенно другой заголовок")

    live_texts = {
        row.text
        for row in db.query(ContentVersion).filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id == str(course.id),
            ContentVersion.superseded_by.is_(None),
        )
    }
    assert "Совершенно другой заголовок" not in live_texts

    staged = db.query(StagedContentVersion).filter(StagedContentVersion.course_id == str(course.id)).all()
    assert [r.text for r in staged] == ["Совершенно другой заголовок"]


def test_every_language_changes_in_the_same_step(db: Session):
    """The whole point. Before promotion nobody has the new text; after
    it, everybody does — there is no moment in between where two
    languages disagree."""
    course = _published_course(db)
    _edit(db, course, "Второе послание к Коринфянам")

    translate_staged_edits(db, course, provider=_Provider())
    before = {locale: _served_text(db, course, locale) for locale in _LOCALES}
    assert all("Второе" not in (text or "") for text in before.values())

    report = promote_ready_fields(db, course)
    assert report.promoted_fields == 1

    after = {locale: _served_text(db, course, locale) for locale in _LOCALES}
    assert after["ru"] == "Второе послание к Коринфянам"
    for locale in ("en", "de", "uk"):
        assert after[locale] is not None
        assert after[locale] != before[locale]

    # And the staging table is empty again: an edit that has landed is
    # not an edit in flight.
    assert db.query(StagedContentVersion).filter(StagedContentVersion.course_id == str(course.id)).count() == 0


def test_a_field_is_not_promoted_while_one_language_is_missing(db: Session):
    """Three of four is not whole. The reader whose language is missing
    is exactly the reader this is for."""
    course = _published_course(db)
    _edit(db, course, "Послание к Галатам")

    text = "Послание к Галатам"
    source_hash = compute_source_hash(text, locale="ru")
    for locale in ("en", "de"):  # uk deliberately absent
        db.add(
            StagedContentVersion(
                entity_type="course",
                entity_id=str(course.id),
                course_id=str(course.id),
                field="title",
                locale=locale,
                text=f"[{locale}] Galatians",
                origin="mt",
                status="ok",
                source_locale="ru",
                source_hash=source_hash,
            )
        )
    db.commit()

    assert promote_ready_fields(db, course).promoted_fields == 0
    assert _served_text(db, course, "ru") == "Первое послание к Коринфянам"


# ---------------------------------------------------------------------------
# 2. The author is not shown their own edit late
# ---------------------------------------------------------------------------


def test_the_author_sees_their_own_edit_immediately(db: Session):
    """A teacher who saves an edit and is shown the previous wording
    concludes the save failed, retypes it, and produces a second save
    identical to the first — which the pipeline correctly treats as no
    change at all. So the editor's view has to show held text."""
    course = _published_course(db)
    _edit(db, course, "Заголовок, который видит только автор")

    assert author_text(db, entity_type="course", entity_id=str(course.id), field="title") == (
        "Заголовок, который видит только автор"
    )

    editor_view = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course",
        entity_ids=[str(course.id)],
        fields=["title"],
        display_locale="ru",
        source_locale="ru",
        prefer_human=True,
    )
    assert editor_view[(str(course.id), "title")] == "Заголовок, который видит только автор"


# ---------------------------------------------------------------------------
# 3. A second edit cannot ride out on the first one's translations
# ---------------------------------------------------------------------------


def test_a_second_edit_discards_the_first_ones_translations(db: Session):
    """Otherwise the mechanism reintroduces, from the inside, exactly the
    defect it exists to prevent: text in one language published beside
    translations of different text."""
    course = _published_course(db)
    _edit(db, course, "Первая правка")
    translate_staged_edits(db, course, provider=_Provider())
    assert db.query(StagedContentVersion).filter(StagedContentVersion.origin == "mt").count() == 3

    _edit(db, course, "Вторая правка")
    assert db.query(StagedContentVersion).filter(StagedContentVersion.origin == "mt").count() == 0
    assert promote_ready_fields(db, course).promoted_fields == 0

    translate_staged_edits(db, course, provider=_Provider())
    assert promote_ready_fields(db, course).promoted_fields == 1
    assert _served_text(db, course, "ru") == "Вторая правка"


def test_reverting_to_the_live_text_cancels_the_edit(db: Session):
    """A teacher who undoes their change should not leave a field stuck
    in flight, waiting for translations of text that is already
    published."""
    course = _published_course(db)
    _edit(db, course, "Черновая правка")
    assert db.query(StagedContentVersion).count() == 1

    _edit(db, course, "Первое послание к Коринфянам")  # back to what is live
    assert db.query(StagedContentVersion).count() == 0


def test_saving_the_same_edit_twice_keeps_its_translations(db: Session):
    """Re-saving a form must not throw away work already paid for."""
    course = _published_course(db)
    _edit(db, course, "Правка")
    translate_staged_edits(db, course, provider=_Provider())
    assert db.query(StagedContentVersion).filter(StagedContentVersion.origin == "mt").count() == 3

    _edit(db, course, "Правка")  # identical save
    assert db.query(StagedContentVersion).filter(StagedContentVersion.origin == "mt").count() == 3


# ---------------------------------------------------------------------------
# 4. Nothing is staged where there is nobody to protect
# ---------------------------------------------------------------------------


def test_a_draft_course_writes_straight_through(db: Session, client):
    """No students, nothing to keep consistent, and staging would only
    delay the author's own view of their own draft."""
    from app.services.content_versions.dual_write import dual_write_entity_content

    _ensure_teacher(db)
    course = Course(id=f"draft-{uuid.uuid4().hex[:8]}", status="draft", source_locale="ru", created_by=TEACHER_ID)
    db.add(course)
    db.commit()

    dual_write_entity_content(
        db,
        entity_type="course",
        entity_id=str(course.id),
        texts={"title": "Черновик курса"},
        fallback_locale="ru",
    )
    db.commit()

    assert db.query(StagedContentVersion).count() == 0
    assert _served_text(db, course, "ru") == "Черновик курса"


def test_leaving_published_releases_whatever_was_held(db: Session):
    """A course pulled back to draft has no readers left to protect, and
    an edit still held would be invisible to its own author's draft —
    they would retype work they had already done."""
    course = _published_course(db)
    _edit(db, course, "Правка перед снятием с публикации")

    released = promote_staged_entity_unconditionally(db, course_id=str(course.id))

    assert released == 1
    assert db.query(StagedContentVersion).count() == 0
    assert _served_text(db, course, "ru") == "Правка перед снятием с публикации"


def test_deleting_the_entity_takes_its_held_edit_with_it(db: Session):
    """An unreleased edit to a deleted entity is text nobody can ever
    see, promote, or find."""
    from app.services.content_versions.write import delete_entity_cv_rows

    course = _published_course(db)
    _edit(db, course, "Правка перед удалением")
    assert db.query(StagedContentVersion).count() == 1

    delete_entity_cv_rows(db, entity_type="course", entity_id=str(course.id))
    db.commit()

    assert db.query(StagedContentVersion).count() == 0


# ---------------------------------------------------------------------------
# 5. An edit that cannot complete says so
# ---------------------------------------------------------------------------


def test_a_translation_that_failed_its_check_marks_the_edit_blocked(db: Session):
    """``needs_review`` does not resolve on its own — the pipeline will
    not re-ask a temperature-0 model the same question. Without a state
    that says so, the edit would sit invisible forever and the teacher
    would have no way to learn why."""
    course = _published_course(db)
    _edit(db, course, "Правка с проблемным переводом")

    text = "Правка с проблемным переводом"
    source_hash = compute_source_hash(text, locale="ru")
    db.add(
        StagedContentVersion(
            entity_type="course",
            entity_id=str(course.id),
            course_id=str(course.id),
            field="title",
            locale="de",
            text="Etwas, das die Prüfung nicht bestanden hat",
            origin="mt",
            status=ContentVersionStatus.NEEDS_REVIEW,
            review_reason="[scripture_marker_mismatch] lost 1",
            source_locale="ru",
            source_hash=source_hash,
        )
    )
    db.commit()

    statuses = staged_status_for_course(db, course)
    assert len(statuses) == 1
    assert statuses[0].state == "blocked"
    assert statuses[0].blocked_locales == ("de",)
    assert set(statuses[0].pending_locales) == {"en", "uk"}

    # And it is not quietly promoted despite the failure.
    assert promote_ready_fields(db, course).blocked_fields == 1
    assert _served_text(db, course, "ru") == "Первое послание к Коринфянам"


def test_a_hand_written_translation_does_not_deadlock_the_edit(db: Session):
    """The pipeline refuses to overwrite a human translation, so waiting
    for a machine one would wait forever. The hand-written wording
    stays and the edit goes out — the alternative is a field frozen
    until somebody re-translates by hand, which serves nobody."""
    course = _published_course(db)
    # Somebody typed the German title themselves.
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="de",
        text="Der erste Brief an die Korinther",
    )
    db.commit()

    _edit(db, course, "Правка при ручном немецком переводе")
    translate_staged_edits(db, course, provider=_Provider())

    statuses = staged_status_for_course(db, course)
    assert statuses[0].state == "ready"
    assert "de" not in statuses[0].pending_locales

    assert promote_ready_fields(db, course).promoted_fields == 1
    assert _served_text(db, course, "de") == "Der erste Brief an die Korinther"
    assert _served_text(db, course, "ru") == "Правка при ручном немецком переводе"
