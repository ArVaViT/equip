"""A translation nobody can find is a translation nobody will accept.

When the structural check refuses a machine translation the row is kept
at ``needs_review`` and not served: the course stays out of the
catalogue, the staged edit stays unpublished, and both wait for a
person. Two endpoints let that person act — ``accept-reviewed`` takes
the ids of rows they have read, ``retry-reviewed`` re-opens rows the
pipeline should ask about again.

Neither had anywhere to get an id from. The queue those endpoints were
written against did not exist, so the only way to name a row was a
hand-written SELECT against production, and in practice that meant
nothing was ever accepted. This is the queue: the text, the source it
came from, the reason it was parked, and what the row belongs to.

The listing filters on exactly the predicates the two mutators apply —
parked, machine-made, still active. A queue offering a row its own
buttons would refuse to touch is worse than no queue, so that agreement
is pinned here rather than left to read alike.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.content_version import ContentVersion
from app.models.course import Chapter, Module
from tests._cv_helpers import (
    make_course_with_text,
    make_quiz_option_with_text,
    make_quiz_question_with_text,
    make_quiz_with_text,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

ENDPOINT = "/api/v1/admin/translations/needs-review"


def _park(
    db: Session,
    *,
    entity_type: str = "daily_challenge_question",
    entity_id: str | None = None,
    field: str = "explanation",
    locale: str = "de",
    text: str = "Johannes 3,17 besagt: 'For God did not send his Son…'",
    origin: str = "mt",
    review_reason: str | None = "[scripture_marker_mismatch] lost 1 (VERSE_a3f9c2b1)",
    source_version_id: uuid.UUID | None = None,
    superseded_by: uuid.UUID | None = None,
) -> ContentVersion:
    row = ContentVersion(
        id=uuid.uuid4(),
        entity_type=entity_type,
        entity_id=entity_id or str(uuid.uuid4()),
        field=field,
        locale=locale,
        text=text,
        origin=origin,
        status="needs_review",
        attempts=1,
        review_reason=review_reason,
        source_locale="en",
        source_hash="y" * 64,
        source_version_id=source_version_id,
        superseded_by=superseded_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _quiz_option_under_a_course(db: Session, *, title: str = "Послание к Римлянам") -> tuple[str, str]:
    """Build the smallest course tree that reaches a quiz option.

    Returns ``(course_id, option_id)``. The option is deep in the tree —
    course → module → chapter → quiz → question → option — which is the
    point: the course a parked row belongs to is several joins away from
    the row, and the queue still has to name it.
    """
    course = make_course_with_text(db, title=title, source_locale="ru", locale="ru")
    module = Module(id=f"mod-{uuid.uuid4().hex[:8]}", course_id=course.id, title="Модуль", order_index=0)
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"ch-{uuid.uuid4().hex[:8]}", module_id=module.id, title="Глава", order_index=0)
    db.add(chapter)
    db.flush()
    quiz = make_quiz_with_text(db, chapter_id=chapter.id, locale="ru")
    question = make_quiz_question_with_text(db, quiz_id=quiz.id, locale="ru")
    option = make_quiz_option_with_text(db, question_id=question.id, locale="ru")
    db.commit()
    return course.id, str(option.id)


def test_an_empty_queue_is_an_answer_not_an_error(admin_client: TestClient):
    """The mutators 404 on nothing-matched because they were asked to
    change something and could not. Being asked what is waiting, and
    answering "nothing", is a success — the panel renders its empty
    state instead of an error."""
    resp = admin_client.get(ENDPOINT)

    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


def test_the_queue_carries_the_text_the_source_and_the_reason(admin_client: TestClient, db: Session):
    """Everything a person needs to judge one row, on the row."""
    source = ContentVersion(
        id=uuid.uuid4(),
        entity_type="daily_challenge_question",
        entity_id=str(uuid.uuid4()),
        field="explanation",
        locale="en",
        text="John 3:17 says: 'For God did not send his Son…'",
        origin="human",
        status="ok",
    )
    db.add(source)
    db.commit()
    parked = _park(db, entity_id=source.entity_id, source_version_id=source.id)

    row = admin_client.get(ENDPOINT).json()["items"][0]

    assert row["id"] == str(parked.id)
    assert row["entity_type"] == "daily_challenge_question"
    assert row["entity_id"] == parked.entity_id
    assert row["field"] == "explanation"
    assert row["locale"] == "de"
    assert row["source_locale"] == "en"
    assert row["review_reason"] == "[scripture_marker_mismatch] lost 1 (VERSE_a3f9c2b1)"
    assert row["text"] == parked.text
    assert row["source_text"] == source.text
    assert row["created_at"] is not None


def test_a_row_without_a_source_link_still_shows_its_source(admin_client: TestClient, db: Session):
    """``source_version_id`` is nullable and ``ON DELETE SET NULL``, so
    rows written before the link existed have none. Falling back to
    whatever is active at the row's source locale is a slightly weaker
    claim — "this is the source now", not "this is what the model saw" —
    and still the text the reviewer has to compare against."""
    entity_id = str(uuid.uuid4())
    db.add(
        ContentVersion(
            id=uuid.uuid4(),
            entity_type="daily_challenge_question",
            entity_id=entity_id,
            field="explanation",
            locale="en",
            text="John 3:17 says so.",
            origin="human",
            status="ok",
        )
    )
    db.commit()
    _park(db, entity_id=entity_id, source_version_id=None)

    row = admin_client.get(ENDPOINT).json()["items"][0]

    assert row["source_text"] == "John 3:17 says so."


def test_platform_content_is_marked_rather_than_left_blank(admin_client: TestClient, db: Session):
    """A Daily Challenge question belongs to no course. Without the
    marker the course column would render empty and read as missing
    data rather than as the answer."""
    _park(db)

    row = admin_client.get(ENDPOINT).json()["items"][0]

    assert row["is_daily_challenge"] is True
    assert row["course_id"] is None
    assert row["course_title"] is None


def test_a_row_deep_in_a_course_names_its_course(admin_client: TestClient, db: Session):
    """An entity id tells a reviewer nothing. The course title is what
    makes the page workable, and it is six joins away from the row."""
    course_id, option_id = _quiz_option_under_a_course(db)
    _park(db, entity_type="quiz_option", entity_id=option_id, field="option_text", locale="uk")

    row = admin_client.get(ENDPOINT).json()["items"][0]

    assert row["is_daily_challenge"] is False
    assert row["course_id"] == course_id
    assert row["course_title"] == "Послание к Римлянам"


def test_the_queue_can_be_narrowed_to_one_language(admin_client: TestClient, db: Session):
    german = _park(db, locale="de")
    _park(db, locale="uk")

    payload = admin_client.get(ENDPOINT, params={"locale": "de"}).json()

    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [str(german.id)]


def test_the_queue_can_be_narrowed_to_one_course(admin_client: TestClient, db: Session):
    """A course's own readiness panel counts these rows; opening the
    queue from there must show that course's rows and no others."""
    course_id, option_id = _quiz_option_under_a_course(db)
    _, other_option_id = _quiz_option_under_a_course(db, title="Другой курс")
    mine = _park(db, entity_type="quiz_option", entity_id=option_id, field="option_text")
    _park(db, entity_type="quiz_option", entity_id=other_option_id, field="option_text")
    _park(db)  # platform content, no course at all

    payload = admin_client.get(ENDPOINT, params={"course_id": course_id}).json()

    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [str(mine.id)]


def test_an_unknown_course_is_a_404_not_an_empty_page(admin_client: TestClient):
    """Silence would read as "nothing is parked here" when the truth is
    "there is no such course" — a typo the operator should be told about."""
    resp = admin_client.get(ENDPOINT, params={"course_id": "no-such-course"})

    assert resp.status_code == 404


def test_the_page_is_a_window_onto_a_total(admin_client: TestClient, db: Session):
    """``total`` counts what matches, not what fits on the page — the UI
    cannot say "12 of 340" otherwise."""
    for _ in range(5):
        _park(db)

    first = admin_client.get(ENDPOINT, params={"limit": 2}).json()
    second = admin_client.get(ENDPOINT, params={"limit": 2, "offset": 2}).json()

    assert first["total"] == second["total"] == 5
    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    assert {item["id"] for item in first["items"]}.isdisjoint({item["id"] for item in second["items"]})


def test_the_page_size_is_capped(admin_client: TestClient):
    """Every row carries two texts. "Give me everything" against a
    catalogue-wide backlog is a response nobody can render and a query
    nobody meant to run."""
    assert admin_client.get(ENDPOINT, params={"limit": 500}).status_code == 422


def test_the_queue_shows_only_rows_the_buttons_can_act_on(admin_client: TestClient, db: Session):
    """A person's own translation is never the pipeline's to redo, and a
    superseded row has already been answered. Both are refused by
    ``accept-reviewed`` and ``retry-reviewed``; listing them would offer
    the reviewer two buttons that do nothing."""
    _park(db, origin="human")
    replacement = _park(db)
    _park(db, superseded_by=replacement.id)

    payload = admin_client.get(ENDPOINT).json()

    assert payload["total"] == 1
    assert payload["items"][0]["id"] == str(replacement.id)


def test_the_queue_is_admin_only(client: TestClient, student_client: TestClient, db: Session):
    """It shows unpublished text from every course on the platform."""
    _park(db)

    assert client.get(ENDPOINT).status_code == 403
    assert student_client.get(ENDPOINT).status_code in (401, 403)
