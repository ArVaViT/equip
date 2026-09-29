"""«Удалить» on a lesson was final from the interface, though the server only
ever stamped ``deleted_at``. The editor offers "Undo" now; this is the route
behind it (2026-09-29)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, Module
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _course_with_lesson(db: Session, course_id: str) -> str:
    db.add(Course(id=course_id, created_by=TEACHER_ID, status="draft", source_locale="ru"))
    db.flush()
    db.add(Chapter(id=f"{course_id}-ch", course_id=course_id, order_index=0, chapter_type="reading", title="Урок 1"))
    db.commit()
    return f"{course_id}-ch"


def test_a_deleted_lesson_comes_back(client: TestClient, db: Session) -> None:
    chapter_id = _course_with_lesson(db, "c-undo")
    base = f"/api/v1/courses/c-undo/chapters/{chapter_id}"

    assert client.delete(base).status_code == 204
    db.expire_all()
    assert db.get(Chapter, chapter_id).deleted_at is not None

    restored = client.post(f"{base}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] == chapter_id
    db.expire_all()
    assert db.get(Chapter, chapter_id).deleted_at is None


def test_a_live_lesson_has_nothing_to_restore(client: TestClient, db: Session) -> None:
    chapter_id = _course_with_lesson(db, "c-undo-live")
    assert client.post(f"/api/v1/courses/c-undo-live/chapters/{chapter_id}/restore").status_code == 404


def test_only_the_courses_teacher_can_restore(client: TestClient, student_client: TestClient, db: Session) -> None:
    chapter_id = _course_with_lesson(db, "c-undo-owner")
    client.delete(f"/api/v1/courses/c-undo-owner/chapters/{chapter_id}")
    denied = student_client.post(f"/api/v1/courses/c-undo-owner/chapters/{chapter_id}/restore")
    assert denied.status_code in (403, 404)


def test_a_lesson_whose_module_is_gone_comes_back_into_the_course(client: TestClient, db: Session) -> None:
    # Binned inside a module, then the module deleted: the lesson must not
    # come back into a module nobody can see.
    db.add(Course(id="c-undo-mod", created_by=TEACHER_ID, status="draft", source_locale="ru"))
    db.flush()
    db.add(Module(id="c-undo-mod-m", course_id="c-undo-mod", title="Модуль", order_index=0))
    db.flush()
    db.add(
        Chapter(
            id="c-undo-mod-ch",
            course_id="c-undo-mod",
            module_id="c-undo-mod-m",
            order_index=0,
            chapter_type="reading",
            title="Урок 1",
        )
    )
    db.commit()
    base = "/api/v1/courses/c-undo-mod/chapters/c-undo-mod-ch"
    assert client.delete(base).status_code == 204
    assert client.delete("/api/v1/courses/c-undo-mod/modules/c-undo-mod-m").status_code == 204

    restored = client.post(f"{base}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["module_id"] is None
    db.expire_all()
    assert db.get(Chapter, "c-undo-mod-ch").module_id is None


def test_a_lesson_whose_module_is_live_goes_back_into_it(client: TestClient, db: Session) -> None:
    db.add(Course(id="c-undo-keep", created_by=TEACHER_ID, status="draft", source_locale="ru"))
    db.flush()
    db.add(Module(id="c-undo-keep-m", course_id="c-undo-keep", title="Модуль", order_index=0))
    db.flush()
    db.add(
        Chapter(
            id="c-undo-keep-ch",
            course_id="c-undo-keep",
            module_id="c-undo-keep-m",
            order_index=0,
            chapter_type="reading",
            title="Урок 1",
        )
    )
    db.commit()
    base = "/api/v1/courses/c-undo-keep/chapters/c-undo-keep-ch"
    assert client.delete(base).status_code == 204
    assert client.post(f"{base}/restore").json()["module_id"] == "c-undo-keep-m"
