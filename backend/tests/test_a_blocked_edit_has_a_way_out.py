"""A held edit whose translation was parked can be released by a person.

On a published course a teacher's edit waits in the staging table until
every language has it. When one translation fails its structural check
(``needs_review``) or runs out of retries (``failed_permanent``) the edit
is ``blocked``: the teacher's card says so, and nothing moves it. The
admin review queue — the one surface built for exactly this decision —
read ``content_versions`` alone, so the blocked edit was in no queue,
accept and retry answered 404 to its ids, and the only exit was the
teacher editing again, which produced the same text and the same
verdict (2026-10-03).

Now the queue lists both tables, marked apart, and the two buttons act
on either. Accepting a held translation runs the promotion for its
course, so an edit that was whole but for that row reaches every
language in the same request.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Course, CourseStatus
from app.models.staged_content_version import StagedContentVersion
from app.models.translation_job import TranslationJob
from app.models.user import User
from app.services.content_versions.read import fetch_cv_entity_texts_with_fallback
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.staged_edits import stage_human_edit
from app.services.translation.hash import compute_source_hash
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    import pytest
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

QUEUE = "/api/v1/admin/translations/needs-review"
ACCEPT = "/api/v1/admin/translations/accept-reviewed"
RETRY = "/api/v1/admin/translations/retry-reviewed"

LIVE_TITLE = "Первое послание к Коринфянам"
NEW_TITLE = "Первое послание апостола Павла к Коринфянам"
PARKED_DE = "Der erste Brief des Apostels Paulus an die Korinther"


def _published_course(db: Session) -> Course:
    """A course being read in four languages."""
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()
    record_human_version(db, entity_type="course", entity_id=course.id, field="title", locale="ru", text=LIVE_TITLE)
    source_hash = compute_source_hash(LIVE_TITLE, locale="ru")
    for locale in ("en", "de", "uk"):
        record_mt_version(
            db,
            entity_type="course",
            entity_id=course.id,
            field="title",
            locale=locale,
            text=f"[{locale}] First Corinthians",
            source_locale="ru",
            source_hash=source_hash,
        )
    db.commit()
    return course


def _hold_edit(db: Session, course: Course, *, text: str = NEW_TITLE) -> str:
    """The teacher's edit, held. Returns the hash its translations must carry."""
    stage_human_edit(
        db,
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        field="title",
        locale="ru",
        text=text,
    )
    db.commit()
    return compute_source_hash(text, locale="ru")


def _held_translation(
    db: Session,
    course: Course,
    *,
    locale: str,
    status: str,
    source_hash: str,
    text: str = "",
    review_reason: str | None = None,
) -> StagedContentVersion:
    row = StagedContentVersion(
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        field="title",
        locale=locale,
        text=text,
        origin="mt",
        status=status,
        review_reason=review_reason,
        source_locale="ru",
        source_hash=source_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _parked_live_row(db: Session) -> ContentVersion:
    """A parked translation of the old kind, in ``content_versions``."""
    row = ContentVersion(
        id=uuid.uuid4(),
        entity_type="daily_challenge_question",
        entity_id=str(uuid.uuid4()),
        field="explanation",
        locale="de",
        text="Johannes 3,17 besagt: 'For God did not send his Son…'",
        origin="mt",
        status="needs_review",
        attempts=1,
        review_reason="[wrong_language]",
        source_locale="en",
        source_hash="y" * 64,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _served(db: Session, course: Course, locale: str) -> str | None:
    return fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course",
        entity_ids=[course.id],
        fields=["title"],
        display_locale=locale,
        source_locale="ru",
        fallback="none",
    ).get((course.id, "title"))


def test_a_held_translation_the_check_parked_is_in_the_queue_marked_as_held(admin_client: TestClient, db: Session):
    course = _published_course(db)
    source_hash = _hold_edit(db, course)
    parked = _held_translation(
        db,
        course,
        locale="de",
        status=ContentVersionStatus.NEEDS_REVIEW,
        source_hash=source_hash,
        text=PARKED_DE,
        review_reason="[wrong_language] reads as nl, not de",
    )

    body = admin_client.get(QUEUE).json()

    assert body["total"] == 1
    (item,) = body["items"]
    assert item["id"] == str(parked.id)
    assert item["held_edit"] is True
    assert item["status"] == "needs_review"
    assert item["text"] == PARKED_DE
    assert item["review_reason"] == "[wrong_language] reads as nl, not de"
    # Judged against the edit it translates, not the wording it replaces.
    assert item["source_text"] == NEW_TITLE
    assert item["course_id"] == course.id
    assert item["course_title"] == LIVE_TITLE


def test_accepting_it_releases_the_edit_in_every_language(admin_client: TestClient, db: Session):
    course = _published_course(db)
    source_hash = _hold_edit(db, course)
    for locale in ("en", "uk"):
        _held_translation(
            db, course, locale=locale, status="ok", source_hash=source_hash, text=f"[{locale}] Paul to Corinth"
        )
    parked = _held_translation(
        db, course, locale="de", status=ContentVersionStatus.NEEDS_REVIEW, source_hash=source_hash, text=PARKED_DE
    )

    response = admin_client.post(ACCEPT, json={"ids": [str(parked.id)]})

    assert response.status_code == 200, response.text
    assert response.json() == {"reset": 1}
    # Nothing left in flight: the whole edit went out, the accepted row with it.
    assert db.query(StagedContentVersion).filter(StagedContentVersion.course_id == course.id).count() == 0
    assert _served(db, course, "ru") == NEW_TITLE
    assert _served(db, course, "de") == PARKED_DE
    assert _served(db, course, "en") == "[en] Paul to Corinth"


def test_accepting_it_does_not_release_a_field_still_waiting_on_another_language(admin_client: TestClient, db: Session):
    course = _published_course(db)
    source_hash = _hold_edit(db, course)
    parked = _held_translation(
        db, course, locale="de", status=ContentVersionStatus.NEEDS_REVIEW, source_hash=source_hash, text=PARKED_DE
    )

    assert admin_client.post(ACCEPT, json={"ids": [str(parked.id)]}).status_code == 200

    db.refresh(parked)
    assert parked.status == ContentVersionStatus.OK
    # English and Ukrainian are still missing: readers keep the old title.
    assert _served(db, course, "ru") == LIVE_TITLE
    assert admin_client.get(QUEUE).json()["total"] == 0


def test_retrying_it_hands_it_back_to_the_pipeline(
    admin_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "TRANSLATION_QUEUE_ENABLED", True)
    course = _published_course(db)
    source_hash = _hold_edit(db, course)
    parked = _held_translation(
        db, course, locale="de", status=ContentVersionStatus.NEEDS_REVIEW, source_hash=source_hash, text=PARKED_DE
    )

    response = admin_client.post(RETRY, json={"ids": [str(parked.id)]})

    assert response.status_code == 200, response.text
    assert response.json() == {"reset": 1}
    db.refresh(parked)
    # ``failed`` with a fresh budget: the one status the staged pass redoes.
    assert (parked.status, parked.attempts) == (ContentVersionStatus.FAILED, 0)
    # And the pass is asked for now, not on somebody else's save.
    assert db.query(TranslationJob).filter(TranslationJob.course_id == course.id).count() == 1


def test_a_held_translation_the_pipeline_gave_up_on_is_listed_with_nothing_to_accept(
    admin_client: TestClient, db: Session
):
    course = _published_course(db)
    source_hash = _hold_edit(db, course)
    gave_up = _held_translation(
        db, course, locale="uk", status=ContentVersionStatus.FAILED_PERMANENT, source_hash=source_hash
    )

    (item,) = admin_client.get(QUEUE).json()["items"]
    assert (item["id"], item["status"], item["held_edit"]) == (str(gave_up.id), "failed_permanent", True)

    # No text came back, so there is nothing a person could be accepting.
    assert admin_client.post(ACCEPT, json={"ids": [str(gave_up.id)]}).status_code == 404
    assert admin_client.post(RETRY, json={"ids": [str(gave_up.id)]}).status_code == 200
    db.refresh(gave_up)
    assert (gave_up.status, gave_up.attempts) == (ContentVersionStatus.FAILED, 0)


def test_the_page_counts_both_tables_and_repeats_no_row(admin_client: TestClient, db: Session):
    course = _published_course(db)
    source_hash = _hold_edit(db, course)
    expected = {str(_parked_live_row(db).id) for _ in range(2)}
    for locale in ("de", "uk"):
        row = _held_translation(
            db, course, locale=locale, status=ContentVersionStatus.NEEDS_REVIEW, source_hash=source_hash, text="x"
        )
        expected.add(str(row.id))

    first = admin_client.get(QUEUE, params={"limit": 3, "offset": 0}).json()
    second = admin_client.get(QUEUE, params={"limit": 3, "offset": 3}).json()

    assert (first["total"], second["total"]) == (4, 4)
    assert (len(first["items"]), len(second["items"])) == (3, 1)
    assert {item["id"] for item in [*first["items"], *second["items"]]} == expected


def test_the_filters_reach_held_rows_too(admin_client: TestClient, db: Session):
    mine = _published_course(db)
    other = _published_course(db)
    for course in (mine, other):
        source_hash = _hold_edit(db, course)
        for locale in ("de", "uk"):
            _held_translation(
                db, course, locale=locale, status=ContentVersionStatus.NEEDS_REVIEW, source_hash=source_hash, text="x"
            )

    by_course = admin_client.get(QUEUE, params={"course_id": mine.id}).json()
    assert by_course["total"] == 2
    assert {item["course_id"] for item in by_course["items"]} == {mine.id}

    by_locale = admin_client.get(QUEUE, params={"locale": "de"}).json()
    assert by_locale["total"] == 2
    assert {item["locale"] for item in by_locale["items"]} == {"de"}
