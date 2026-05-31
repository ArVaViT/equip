"""Sprint 7 — bilingual review queue + cv editor endpoint tests.

Covers:
- list filter by status + missing-RU
- bilingual view: parallel EN/RU cells, missing locale → empty cell
- cv upsert: question_text + explanation + option_text
- cv upsert refuses rejected questions (409)
- cv upsert refuses missing option_id for option_text (400)
- promote unaffected (existing tests pin it)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.models.daily_challenge import (
    DailyChallengeOption,
    DailyChallengeQuestion,
)
from app.models.user import User, UserRole
from app.services.content_versions.write import record_human_version

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


@pytest.fixture
def author(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"dc-bilingual-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Bilingual Author",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


def _seed_question(
    db: Session,
    *,
    author_id: uuid.UUID,
    status: str = "doctrinally_reviewed",
    rejected: bool = False,
    en_text: str | None = "Romans 8 question?",
    ru_text: str | None = "Вопрос про Римлянам 8?",
    en_explanation: str | None = "EN explanation",
    ru_explanation: str | None = "RU объяснение",
) -> DailyChallengeQuestion:
    q = DailyChallengeQuestion(
        question_type="multiple_choice",
        status=status,
        published_at=datetime.now(UTC) if status == "published" else None,
        published_by=author_id if status == "published" else None,
        created_by=author_id,
        rejected=rejected,
        bible_book="Romans",
        bible_chapter=8,
        bible_verse_from=1,
        bible_verse_to=1,
        source_locale="en",
    )
    db.add(q)
    db.flush()
    if en_text:
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(q.id),
            field="question_text",
            locale="en",
            text=en_text,
            authored_by=author_id,
        )
    if ru_text:
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(q.id),
            field="question_text",
            locale="ru",
            text=ru_text,
            authored_by=author_id,
        )
    if en_explanation:
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(q.id),
            field="explanation",
            locale="en",
            text=en_explanation,
            authored_by=author_id,
        )
    if ru_explanation:
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(q.id),
            field="explanation",
            locale="ru",
            text=ru_explanation,
            authored_by=author_id,
        )

    for idx, (text, is_correct) in enumerate([("A", True), ("B", False), ("C", False), ("D", False)]):
        o = DailyChallengeOption(question_id=q.id, is_correct=is_correct, order_index=idx)
        db.add(o)
        db.flush()
        record_human_version(
            db,
            entity_type="daily_challenge_option",
            entity_id=str(o.id),
            field="option_text",
            locale="en",
            text=text,
            authored_by=author_id,
        )
    db.commit()
    db.refresh(q)
    return q


# ── queue list ────────────────────────────────────────────────────────


def test_queue_lists_by_status(db: Session, author: User, teacher: User, client: TestClient):
    _seed_question(db, author_id=author.id, status="doctrinally_reviewed")
    _seed_question(db, author_id=author.id, status="draft")
    resp = client.get("/api/v1/admin/daily-challenge/questions?status=doctrinally_reviewed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert all(i["status"] == "doctrinally_reviewed" for i in body["items"])


def test_queue_missing_ru_filter(db: Session, author: User, teacher: User, client: TestClient):
    _seed_question(db, author_id=author.id, ru_text=None)  # missing RU
    _seed_question(db, author_id=author.id)  # has both
    resp = client.get("/api/v1/admin/daily-challenge/questions?only_missing_ru=true")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["has_ru"] is False
    assert body["items"][0]["has_en"] is True


def test_queue_excludes_rejected_by_default(db: Session, author: User, teacher: User, client: TestClient):
    _seed_question(db, author_id=author.id, rejected=True)
    _seed_question(db, author_id=author.id)
    resp = client.get("/api/v1/admin/daily-challenge/questions")
    body = resp.json()
    assert all(i["rejected"] is False for i in body["items"])
    assert body["total"] == 1


# ── bilingual view ───────────────────────────────────────────────────


def test_bilingual_view_returns_parallel_cells(db: Session, author: User, teacher: User, client: TestClient):
    q = _seed_question(db, author_id=author.id)
    resp = client.get(f"/api/v1/admin/daily-challenge/questions/{q.id}/bilingual")
    assert resp.status_code == 200
    body = resp.json()
    assert body["question_text"]["en"]["text"].startswith("Romans 8")
    assert "Римлянам" in body["question_text"]["ru"]["text"]
    assert body["question_text"]["en"]["origin"] == "human"
    assert all(o["en"]["text"] for o in body["options"])
    # Options have no RU cv → empty cells.
    assert all(o["ru"]["text"] == "" for o in body["options"])
    assert all(o["ru"]["cv_id"] is None for o in body["options"])


def test_bilingual_view_returns_empty_cell_when_locale_missing(
    db: Session, author: User, teacher: User, client: TestClient
):
    q = _seed_question(db, author_id=author.id, ru_text=None)
    resp = client.get(f"/api/v1/admin/daily-challenge/questions/{q.id}/bilingual")
    body = resp.json()
    assert body["question_text"]["ru"]["text"] == ""
    assert body["question_text"]["ru"]["cv_id"] is None
    assert body["question_text"]["ru"]["origin"] is None


# ── cv upsert ───────────────────────────────────────────────────────


def test_cv_upsert_creates_new_locale(db: Session, author: User, teacher: User, client: TestClient):
    q = _seed_question(db, author_id=author.id, ru_text=None)
    resp = client.post(
        f"/api/v1/admin/daily-challenge/questions/{q.id}/cv",
        json={"field": "question_text", "locale": "ru", "text": "Новый русский перевод"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Новый русский перевод"
    assert body["locale"] == "ru"
    assert body["origin"] == "human"
    # Followed up by GET → the RU cell now populated.
    view = client.get(f"/api/v1/admin/daily-challenge/questions/{q.id}/bilingual").json()
    assert view["question_text"]["ru"]["text"] == "Новый русский перевод"


def test_cv_upsert_supersedes_existing(db: Session, author: User, teacher: User, client: TestClient):
    q = _seed_question(db, author_id=author.id)
    resp = client.post(
        f"/api/v1/admin/daily-challenge/questions/{q.id}/cv",
        json={"field": "question_text", "locale": "ru", "text": "Полностью переписанный перевод"},
    )
    assert resp.status_code == 200
    view = client.get(f"/api/v1/admin/daily-challenge/questions/{q.id}/bilingual").json()
    assert view["question_text"]["ru"]["text"] == "Полностью переписанный перевод"


def test_cv_upsert_option_text_requires_option_id(db: Session, author: User, teacher: User, client: TestClient):
    q = _seed_question(db, author_id=author.id)
    resp = client.post(
        f"/api/v1/admin/daily-challenge/questions/{q.id}/cv",
        json={"field": "option_text", "locale": "ru", "text": "Вариант на русском"},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "validation.failed"


def test_cv_upsert_option_text_with_valid_option_persists(db: Session, author: User, teacher: User, client: TestClient):
    q = _seed_question(db, author_id=author.id)
    option_id = q.options[0].id
    resp = client.post(
        f"/api/v1/admin/daily-challenge/questions/{q.id}/cv",
        json={
            "field": "option_text",
            "locale": "ru",
            "text": "Вариант на русском",
            "option_id": str(option_id),
        },
    )
    assert resp.status_code == 200
    view = client.get(f"/api/v1/admin/daily-challenge/questions/{q.id}/bilingual").json()
    edited = next(o for o in view["options"] if o["id"] == str(option_id))
    assert edited["ru"]["text"] == "Вариант на русском"


def test_cv_upsert_refuses_rejected_question(db: Session, author: User, teacher: User, client: TestClient):
    q = _seed_question(db, author_id=author.id, rejected=True)
    resp = client.post(
        f"/api/v1/admin/daily-challenge/questions/{q.id}/cv",
        json={"field": "question_text", "locale": "ru", "text": "irrelevant"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "validation.failed"


def test_cv_upsert_refuses_unknown_option_id(db: Session, author: User, teacher: User, client: TestClient):
    q = _seed_question(db, author_id=author.id)
    resp = client.post(
        f"/api/v1/admin/daily-challenge/questions/{q.id}/cv",
        json={
            "field": "option_text",
            "locale": "ru",
            "text": "Вариант",
            "option_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 400
