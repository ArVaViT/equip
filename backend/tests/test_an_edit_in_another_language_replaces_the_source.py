# ruff: noqa: RUF001
# Russian on purpose: the course is Russian and the detector has to see it.
"""An author's edit written in another language replaces the source (2026-10-17).

The story: a teacher's course is in Russian. They open a module, and the
editor shows its Russian name; they type the new name in English — their
interface is English, or they simply write it that way. The detector
files the text by what it is in, so it became an English row beside the
Russian one, and three things followed without anybody saying so:

* the Russian name stayed active and was what Russian readers kept
  reading;
* the pipeline kept translating outward from the Russian, so German and
  Ukrainian readers kept reading the old name too — only English changed;
* the editor reopened on the earliest person-written row, the Russian,
  and the edit looked lost.

Now the edit replaces the source it was typed over: the Russian row is
superseded by the English one (straight away on a draft, at release on a
live course, where the Russian side gets a translation of the new words
like every other language), and the author sees their own words.

A hand translation in a third language is still left alone, as it is
when the source is edited in its own language.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion
from app.models.course import Course, CourseStatus
from app.models.user import User
from app.services.content_versions import dual_write_entity_content
from app.services.content_versions.read import fetch_cv_entity_texts_with_fallback
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.staged_edits import author_text, promote_ready_fields, staged_status_for_course
from app.services.translation.hash import compute_source_hash
from app.services.translation.service import reset_translation_provider_cache
from app.services.translation.staged_pipeline import translate_staged_edits
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.services.translation.protocol import TranslationRequest, TranslationResult

PREFIX = "/api/v1/courses"
RU_NAME = "Деяния святых апостолов и первая церковь в Иерусалиме"
EN_NAME = "The Acts of the Apostles and the first church in Jerusalem"
OLD_TITLE = "Первое послание к Коринфянам"
NEW_TITLE_EN = "The First Letter to the Corinthians, read slowly"


#: What the translator makes of NEW_TITLE_EN in each language — real
#: wording, so the pipeline's language check passes it.
TRANSLATED = {
    "ru": "Первое послание к Коринфянам, прочитанное медленно",
    "uk": "Перше послання до коринтян, прочитане повільно і уважно",
    "de": "Der erste Brief an die Korinther, langsam gelesen",
}


class _Provider:
    name = "recording"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        from app.services.translation.protocol import TranslationResult as Result

        return Result(text=TRANSLATED[request.target_locale], model="test")


def _human_rows(db: Session, entity_type: str, entity_id: str, field: str) -> list[tuple[str, str]]:
    db.expire_all()
    rows = (
        db.query(ContentVersion.locale, ContentVersion.text)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.origin == "human",
            ContentVersion.superseded_by.is_(None),
        )
        .order_by(ContentVersion.locale)
        .all()
    )
    return [(locale, text) for locale, text in rows]


# ─── A draft: the edit writes straight through ──────────────────────────


def _draft_course_with_module(client: TestClient, db: Session) -> tuple[str, str]:
    created = client.post(PREFIX, json={"title": "Деяния"})
    assert created.status_code == 201, created.text
    course_id: str = created.json()["id"]
    course = db.get(Course, course_id)
    assert course is not None
    course.source_locale = "ru"
    db.commit()
    module = client.post(f"{PREFIX}/{course_id}/modules", json={"title": RU_NAME})
    assert module.status_code == 201, module.text
    module_id: str = module.json()["id"]
    assert _human_rows(db, "module", module_id, "title") == [("ru", RU_NAME)]
    return course_id, module_id


def test_a_draft_module_renamed_in_english_drops_the_russian_name(client: TestClient, db: Session) -> None:
    course_id, module_id = _draft_course_with_module(client, db)

    saved = client.put(f"{PREFIX}/{course_id}/modules/{module_id}", json={"title": EN_NAME})

    assert saved.status_code == 200, saved.text
    # Before: [("en", EN_NAME), ("ru", RU_NAME)] — the old name still live.
    assert _human_rows(db, "module", module_id, "title") == [("en", EN_NAME)]
    assert saved.json()["title"] == EN_NAME


def test_the_editor_reopens_on_the_new_name(client: TestClient, db: Session) -> None:
    course_id, module_id = _draft_course_with_module(client, db)
    assert client.put(f"{PREFIX}/{course_id}/modules/{module_id}", json={"title": EN_NAME}).status_code == 200

    module = client.get(f"{PREFIX}/{course_id}/modules/{module_id}", params={"source": 1})
    course = client.get(f"{PREFIX}/{course_id}", params={"source": 1})

    assert module.status_code == 200, module.text
    assert module.json()["title"] == EN_NAME
    assert course.status_code == 200, course.text
    assert [m["title"] for m in course.json()["modules"]] == [EN_NAME]


def test_an_edit_in_the_courses_language_leaves_a_hand_translation_alone(client: TestClient, db: Session) -> None:
    course_id, module_id = _draft_course_with_module(client, db)
    record_human_version(
        db, entity_type="module", entity_id=module_id, field="title", locale="de", text="Apostelgeschichte"
    )
    db.commit()

    new_ru = "Деяния апостолов: от Вознесения до Рима, глава за главой"
    assert client.put(f"{PREFIX}/{course_id}/modules/{module_id}", json={"title": new_ru}).status_code == 200

    assert _human_rows(db, "module", module_id, "title") == [("de", "Apostelgeschichte"), ("ru", new_ru)]


def test_a_short_heading_saves_on_a_field_already_written_in_two_languages(db: Session) -> None:
    """A field left with a person's text in two locales (an edit filed in
    another language before this fix) raised MultipleResultsFound on the
    next save the detector could not classify — a 500 for typing «12»."""
    _ensure_teacher(db)
    course = Course(
        id=f"c-{uuid.uuid4().hex[:8]}", status=CourseStatus.DRAFT, source_locale="ru", created_by=TEACHER_ID
    )
    db.add(course)
    db.commit()
    cid = str(course.id)
    record_human_version(db, entity_type="course", entity_id=cid, field="title", locale="ru", text=OLD_TITLE)
    db.commit()
    record_human_version(db, entity_type="course", entity_id=cid, field="title", locale="en", text=NEW_TITLE_EN)
    db.commit()

    dual_write_entity_content(db, entity_type="course", entity_id=cid, texts={"title": "12"}, fallback_locale="ru")
    db.commit()

    # Filed under the field's source — the Russian the editor shows — not
    # under the newer English row, which stays as it was.
    assert _human_rows(db, "course", cid, "title") == [("en", NEW_TITLE_EN), ("ru", "12")]


def test_the_sources_own_words_filed_under_another_language_change_nothing(db: Session) -> None:
    _ensure_teacher(db)
    course = Course(
        id=f"c-{uuid.uuid4().hex[:8]}", status=CourseStatus.DRAFT, source_locale="ru", created_by=TEACHER_ID
    )
    db.add(course)
    db.commit()
    cid = str(course.id)
    record_human_version(db, entity_type="course", entity_id=cid, field="title", locale="ru", text="Иов")
    db.commit()

    record_human_version(
        db, entity_type="course", entity_id=cid, field="title", locale="uk", text="Иов", course_locale="ru"
    )
    db.commit()

    assert _human_rows(db, "course", cid, "title") == [("ru", "Иов")]


def test_the_block_editor_reopens_on_the_authors_words(client: TestClient, db: Session) -> None:
    """Lesson text has its own resolver; it showed the machine's Russian
    back, and an autosave of that would have made it the source."""
    created = client.post(PREFIX, json={"title": "Деяния"})
    course_id = created.json()["id"]
    course = db.get(Course, course_id)
    assert course is not None
    course.source_locale = "ru"
    db.commit()
    chapter = client.post(f"{PREFIX}/{course_id}/chapters", json={"title": RU_NAME})
    assert chapter.status_code == 201, chapter.text
    chapter_id = chapter.json()["id"]
    block = client.post(
        f"/api/v1/blocks/chapter/{chapter_id}",
        json={"block_type": "text", "order_index": 0, "content": f"<p>{RU_NAME}</p>"},
    )
    assert block.status_code == 201, block.text
    block_id = block.json()["id"]
    edited = client.put(f"/api/v1/blocks/{block_id}", json={"content": f"<p>{EN_NAME}</p>"})
    assert edited.status_code == 200, edited.text
    # The pipeline's Russian translation of the English edit.
    record_mt_version(
        db,
        entity_type="chapter_block",
        entity_id=block_id,
        field="content",
        locale="ru",
        text=f"<p>{TRANSLATED['ru']}</p>",
        source_locale="en",
        source_hash=compute_source_hash(f"<p>{EN_NAME}</p>", locale="en"),
    )
    db.commit()

    shown = client.get(f"/api/v1/blocks/chapter/{chapter_id}", params={"source": 1})

    assert shown.status_code == 200, shown.text
    assert [b["content"] for b in shown.json()] == [f"<p>{EN_NAME}</p>"]


# ─── A live course: the edit waits, then replaces the source ────────────


@pytest.fixture()
def _translation_on(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _published_course(db: Session) -> Course:
    """A Russian course read in four languages: the Russian title a person
    wrote, and a machine translation of it in each of the others."""
    _ensure_teacher(db)
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()
    cid = str(course.id)
    record_human_version(db, entity_type="course", entity_id=cid, field="title", locale="ru", text=OLD_TITLE)
    source_hash = compute_source_hash(OLD_TITLE, locale="ru")
    for locale in ("en", "de", "uk"):
        record_mt_version(
            db,
            entity_type="course",
            entity_id=cid,
            field="title",
            locale=locale,
            text=f"[{locale}] First Corinthians",
            source_locale="ru",
            source_hash=source_hash,
        )
    db.commit()
    return course


def _served(db: Session, course: Course, locale: str) -> Any:
    db.expire_all()
    return fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course",
        entity_ids=[str(course.id)],
        fields=["title"],
        display_locale=locale,
        source_locale="ru",
        fallback="none",
    ).get((str(course.id), "title"))


def _edit_in_english(db: Session, course: Course) -> None:
    dual_write_entity_content(
        db, entity_type="course", entity_id=str(course.id), texts={"title": NEW_TITLE_EN}, fallback_locale="ru"
    )
    db.commit()


@pytest.mark.usefixtures("_translation_on")
def test_a_live_course_edited_in_english_changes_every_language_including_russian(db: Session) -> None:
    course = _published_course(db)
    _edit_in_english(db, course)
    # The author sees their words at once; readers keep the old ones.
    assert author_text(db, entity_type="course", entity_id=str(course.id), field="title") == NEW_TITLE_EN
    assert _served(db, course, "ru") == OLD_TITLE

    translate_staged_edits(db, course, provider=_Provider())

    statuses = staged_status_for_course(db, course)
    # Before: «ready» at once with Russian counted as a hand translation,
    # and the old Russian title released beside the new English one.
    assert [s.state for s in statuses] == ["ready"]
    assert promote_ready_fields(db, course).promoted_fields == 1

    assert _served(db, course, "en") == NEW_TITLE_EN
    assert _served(db, course, "ru") == TRANSLATED["ru"]
    assert _served(db, course, "de") == TRANSLATED["de"]
    assert _human_rows(db, "course", str(course.id), "title") == [("en", NEW_TITLE_EN)]


@pytest.mark.usefixtures("_translation_on")
def test_a_hand_translation_in_a_third_language_survives_the_edit(db: Session) -> None:
    course = _published_course(db)
    record_human_version(
        db, entity_type="course", entity_id=str(course.id), field="title", locale="de", text="Der erste Korintherbrief"
    )
    db.commit()
    _edit_in_english(db, course)

    translate_staged_edits(db, course, provider=_Provider())
    assert promote_ready_fields(db, course).promoted_fields == 1

    assert _served(db, course, "de") == "Der erste Korintherbrief"
    assert _served(db, course, "ru") == TRANSLATED["ru"]
    assert _human_rows(db, "course", str(course.id), "title") == [
        ("de", "Der erste Korintherbrief"),
        ("en", NEW_TITLE_EN),
    ]


@pytest.mark.usefixtures("_translation_on")
def test_the_authors_source_view_shows_their_words_not_the_machines(db: Session) -> None:
    course = _published_course(db)
    _edit_in_english(db, course)
    translate_staged_edits(db, course, provider=_Provider())
    promote_ready_fields(db, course)

    def read(display: str) -> Any:
        db.expire_all()
        return fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="course",
            entity_ids=[str(course.id)],
            fields=["title"],
            display_locale=display,
            source_locale="ru",
            prefer_human=True,
        ).get((str(course.id), "title"))

    # Asked for the source language: what they typed, not «[ru]…».
    assert read("ru") == NEW_TITLE_EN
    # Asked for another language (the owner's German PDF): German.
    assert read("de") == TRANSLATED["de"]


# ─── The same story through the API, and past the publication gate ──────
#
# The cases above exercise the services. These walk the two paths a
# teacher actually takes — the editor's PUT on a live course, and a draft
# rewritten before it is published — and read the result the way the
# readers and the gate do (2026-10-19).


def _module_title(db: Session, module_id: str, locale: str) -> Any:
    db.expire_all()
    return fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="module",
        entity_ids=[module_id],
        fields=["title"],
        display_locale=locale,
        source_locale="ru",
        fallback="none",
    ).get((module_id, "title"))


def _live_course_with_module(client: TestClient, db: Session) -> tuple[str, str]:
    """A published Russian course whose module is read in four languages."""
    course_id, module_id = _draft_course_with_module(client, db)
    source_hash = compute_source_hash(RU_NAME, locale="ru")
    for locale in ("en", "de", "uk"):
        record_mt_version(
            db,
            entity_type="module",
            entity_id=module_id,
            field="title",
            locale=locale,
            text=f"[{locale}] Acts and the first church",
            source_locale="ru",
            source_hash=source_hash,
        )
    course = db.get(Course, course_id)
    assert course is not None
    course.status = CourseStatus.PUBLISHED
    db.commit()
    return course_id, module_id


class _ModuleProvider:
    name = "recording"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        from app.services.translation.protocol import TranslationResult as Result

        return Result(text=f"{TRANSLATED[request.target_locale]} ({request.target_locale})", model="test")


@pytest.mark.usefixtures("_translation_on")
def test_a_live_module_renamed_in_english_through_the_editor_reaches_every_reader(
    client: TestClient, db: Session
) -> None:
    course_id, module_id = _live_course_with_module(client, db)

    saved = client.put(f"{PREFIX}/{course_id}/modules/{module_id}", json={"title": EN_NAME})
    assert saved.status_code == 200, saved.text

    # Held: every reader, the Russian one included, keeps the old name;
    # the author's own view already shows the new words.
    assert _module_title(db, module_id, "ru") == RU_NAME
    assert _module_title(db, module_id, "en") == "[en] Acts and the first church"
    assert saved.json()["title"] == EN_NAME
    editor = client.get(f"{PREFIX}/{course_id}/modules/{module_id}", params={"source": 1})
    assert editor.status_code == 200, editor.text
    assert editor.json()["title"] == EN_NAME

    course = db.get(Course, course_id)
    assert course is not None
    translate_staged_edits(db, course, provider=_ModuleProvider())
    assert [s.state for s in staged_status_for_course(db, course)] == ["ready"]
    assert promote_ready_fields(db, course).promoted_fields == 1

    # Released in the same step everywhere: the Russian side carries a
    # translation of the English words, not the Russian they replaced.
    assert _module_title(db, module_id, "en") == EN_NAME
    assert _module_title(db, module_id, "ru") == f"{TRANSLATED['ru']} (ru)"
    assert _module_title(db, module_id, "de") == f"{TRANSLATED['de']} (de)"
    assert _module_title(db, module_id, "uk") == f"{TRANSLATED['uk']} (uk)"
    assert _human_rows(db, "module", module_id, "title") == [("en", EN_NAME)]
    # Nothing left in flight, and the editor still shows the author's words.
    assert staged_status_for_course(db, course) == []
    editor = client.get(f"{PREFIX}/{course_id}/modules/{module_id}", params={"source": 1})
    assert editor.json()["title"] == EN_NAME


@pytest.mark.usefixtures("_translation_on")
def test_a_draft_rewritten_in_english_is_planned_and_gated_from_the_english(client: TestClient, db: Session) -> None:
    """The publication gate and the plan both take the field's own source —
    the English the author wrote last — not the course's declared Russian,
    which the edit retired. Otherwise the gate would wait for an English
    translation of a Russian text that no longer exists."""
    from app.services.translation.completeness import course_translation_completeness
    from app.services.translation.course_pipeline import plan_course_tasks

    course_id, module_id = _draft_course_with_module(client, db)
    assert client.put(f"{PREFIX}/{course_id}/modules/{module_id}", json={"title": EN_NAME}).status_code == 200
    course = db.get(Course, course_id)
    assert course is not None

    gaps = course_translation_completeness(db, course).gaps
    module_gaps = {(g.locale, g.reason) for g in gaps if g.entity_type == "module" and g.field == "title"}
    assert module_gaps == {("ru", "missing"), ("de", "missing"), ("uk", "missing")}

    tasks = [t for t in plan_course_tasks(db, course) if t.entity_type == "module" and t.field == "title"]
    assert {(t.source_locale, t.target_locale) for t in tasks} == {("en", "ru"), ("en", "de"), ("en", "uk")}
    assert {t.text for t in tasks} == {EN_NAME}
