"""The one-row routes cannot break the course's one sequence (2026-10-17).

Since fc1525d1 a module and a lesson outside any module share one
numbering space, and only ``PUT /courses/{id}/outline`` writes it. The
older routes — ``PUT .../modules/{id}`` and ``PUT .../chapters/{id}`` —
still took an ``order_index`` and wrote it as is. Before the shared
sequence the editor reordered modules by sending each its index among the
modules (0, 1, 2…), and a tab opened before the deploy still sends that:
in the shared space such a number lands a module in front of a loose
lesson, or ties with one. So those routes now refuse a new place outside
a module (409, nothing written), and keep doing what the module editor
relies on — renumbering lessons inside one module, where a number only
orders the module's own lessons.

And a lesson brought back from the bin never shares a number with a
module that took its place meanwhile.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.models.course import Chapter, Module
from app.services.course_service._outline import live_spine

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

PREFIX = "/api/v1/courses"


def _course(client: TestClient) -> str:
    created = client.post(PREFIX, json={"title": "Course"})
    assert created.status_code == 201, created.text
    course_id: str = created.json()["id"]
    return course_id


def _module(client: TestClient, course_id: str, title: str) -> str:
    created = client.post(f"{PREFIX}/{course_id}/modules", json={"title": title})
    assert created.status_code == 201, created.text
    module_id: str = created.json()["id"]
    return module_id


def _lesson(client: TestClient, course_id: str, title: str, module_id: str | None = None) -> str:
    url = f"{PREFIX}/{course_id}/modules/{module_id}/chapters" if module_id else f"{PREFIX}/{course_id}/chapters"
    created = client.post(url, json={"title": title})
    assert created.status_code == 201, created.text
    chapter_id: str = created.json()["id"]
    return chapter_id


def _reads(db: Session, course_id: str) -> list[str]:
    """The course as it reads: modules as ``[id]``, lessons by title."""
    db.expire_all()
    out: list[str] = []
    for run in live_spine(db, course_id).runs:
        if run.module is not None:
            out.append(f"[{run.module.id}]")
        out.extend(c.title for c in run.chapters)
    return out


def _numbers(db: Session, course_id: str) -> list[int]:
    """The numbers of the course's places: its modules and loose lessons."""
    db.expire_all()
    modules = db.query(Module.order_index).filter(Module.course_id == course_id, Module.deleted_at.is_(None))
    loose = db.query(Chapter.order_index).filter(
        Chapter.course_id == course_id, Chapter.module_id.is_(None), Chapter.deleted_at.is_(None)
    )
    return [n for (n,) in modules] + [n for (n,) in loose]


def _row(db: Session, model: type[Module] | type[Chapter], row_id: str) -> Any:
    db.expire_all()
    row = db.get(model, row_id)
    assert row is not None
    return row


def _put(client: TestClient, url: str, body: dict[str, Any]) -> Any:
    return client.put(url, json=body)


class TestAModulesPlace:
    def test_an_index_among_modules_from_an_old_tab_is_refused(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        first = _module(client, course_id, "First")
        _lesson(client, course_id, "a", first)
        _lesson(client, course_id, "loose")
        second = _module(client, course_id, "Second")
        before = _reads(db, course_id)

        # «Second» is the second module: the old editor sent it index 1,
        # which in the shared space is in front of the loose lesson.
        refused = _put(client, f"{PREFIX}/{course_id}/modules/{second}", {"order_index": 1})

        assert refused.status_code == 409, refused.text
        assert "outline" in refused.text
        assert _reads(db, course_id) == before

    def test_the_number_it_already_has_is_no_move(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        module = _module(client, course_id, "M")
        _lesson(client, course_id, "loose")
        current = _row(db, Module, module).order_index

        saved = _put(client, f"{PREFIX}/{course_id}/modules/{module}", {"title": "Renamed", "order_index": current})

        assert saved.status_code == 200, saved.text
        assert saved.json()["title"] == "Renamed"
        assert saved.json()["order_index"] == current

    def test_a_null_number_changes_nothing_instead_of_failing(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        module = _module(client, course_id, "M")
        before = _reads(db, course_id)

        saved = _put(client, f"{PREFIX}/{course_id}/modules/{module}", {"order_index": None})

        assert saved.status_code == 200, saved.text
        assert _reads(db, course_id) == before


class TestALessonsPlace:
    def test_a_loose_lesson_is_not_renumbered_alone(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        module = _module(client, course_id, "M")
        _lesson(client, course_id, "a", module)
        loose = _lesson(client, course_id, "loose")
        before = _reads(db, course_id)

        refused = _put(client, f"{PREFIX}/{course_id}/chapters/{loose}", {"order_index": 0})

        assert refused.status_code == 409, refused.text
        assert _reads(db, course_id) == before

    def test_taken_out_of_a_module_with_a_number_is_refused(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        module = _module(client, course_id, "M")
        a = _lesson(client, course_id, "a", module)
        before = _reads(db, course_id)

        refused = _put(client, f"{PREFIX}/{course_id}/chapters/{a}", {"module_id": None, "order_index": 0})

        assert refused.status_code == 409, refused.text
        assert _reads(db, course_id) == before
        assert _row(db, Chapter, a).module_id == module

    def test_taken_out_of_a_module_without_a_number_still_stays_beside_it(
        self, client: TestClient, db: Session
    ) -> None:
        course_id = _course(client)
        first = _module(client, course_id, "First")
        a = _lesson(client, course_id, "a", first)
        second = _module(client, course_id, "Second")

        saved = _put(client, f"{PREFIX}/{course_id}/chapters/{a}", {"module_id": None})

        assert saved.status_code == 200, saved.text
        assert _reads(db, course_id) == [f"[{first}]", "a", f"[{second}]"]

    def test_the_title_saves_with_the_number_echoed_back(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        loose = _lesson(client, course_id, "loose")
        current = _row(db, Chapter, loose).order_index

        saved = _put(client, f"{PREFIX}/{course_id}/chapters/{loose}", {"title": "Renamed", "order_index": current})

        assert saved.status_code == 200, saved.text
        assert saved.json()["title"] == "Renamed"

    def test_a_null_number_changes_nothing_instead_of_failing(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        module = _module(client, course_id, "M")
        a = _lesson(client, course_id, "a", module)

        saved = _put(client, f"{PREFIX}/{course_id}/chapters/{a}", {"order_index": None})

        assert saved.status_code == 200, saved.text

    def test_the_module_editor_still_reorders_a_modules_lessons(self, client: TestClient, db: Session) -> None:
        # What `useModuleEditor` sends: the numbers the lessons already had,
        # handed out again in the new order (`reuseOrderNumbers`).
        course_id = _course(client)
        module = _module(client, course_id, "M")
        a = _lesson(client, course_id, "a", module)
        b = _lesson(client, course_id, "b", module)
        loose = _lesson(client, course_id, "loose")
        na, nb = _row(db, Chapter, a).order_index, _row(db, Chapter, b).order_index

        assert _put(client, f"{PREFIX}/{course_id}/chapters/{b}", {"order_index": na}).status_code == 200
        assert _put(client, f"{PREFIX}/{course_id}/chapters/{a}", {"order_index": nb}).status_code == 200

        assert _reads(db, course_id) == [f"[{module}]", "b", "a", "loose"]
        assert db.get(Chapter, loose) is not None


class TestALessonBackFromTheBin:
    def test_does_not_share_its_number_with_a_module_added_meanwhile(self, client: TestClient, db: Session) -> None:
        # Delete the last, loose lesson; add a module (it takes the freed
        # tail number); Undo. A tie between a module and a loose lesson
        # reads module first by accident, not by anybody's choice — the
        # lesson goes to the tail instead.
        course_id = _course(client)
        first = _module(client, course_id, "First")
        _lesson(client, course_id, "a", first)
        loose = _lesson(client, course_id, "loose")
        assert client.delete(f"{PREFIX}/{course_id}/chapters/{loose}").status_code == 204
        added = _module(client, course_id, "Added")

        restored = client.post(f"{PREFIX}/{course_id}/chapters/{loose}/restore")

        assert restored.status_code == 200, restored.text
        numbers = _numbers(db, course_id)
        assert len(numbers) == len(set(numbers)), numbers
        assert _reads(db, course_id) == [f"[{first}]", "a", f"[{added}]", "loose"]

    def test_comes_back_to_its_place_when_nobody_took_it(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        first = _module(client, course_id, "First")
        loose = _lesson(client, course_id, "loose")
        second = _module(client, course_id, "Second")
        assert client.delete(f"{PREFIX}/{course_id}/chapters/{loose}").status_code == 204

        assert client.post(f"{PREFIX}/{course_id}/chapters/{loose}/restore").status_code == 200

        assert _reads(db, course_id) == [f"[{first}]", "loose", f"[{second}]"]
