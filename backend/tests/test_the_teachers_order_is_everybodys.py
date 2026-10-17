"""The order the teacher set is the order everybody reads (2026-10-16).

Vadym's decision: one order for everybody. A lesson outside a module
stays exactly where the teacher put it — between two modules, before the
first, after the last — and the student walks the same sequence: "next
lesson", the sequential lock, the course page, the PDF.

What used to go wrong, each pinned below:

* the editor reordered modules and lessons with one request per row, in
  two number spaces nothing reconciled; a module moved without its
  lessons being renumbered left a loose lesson on the wrong side of it.
  Now ``PUT /courses/{id}/outline`` writes the whole sequence at once;
* a lesson taken out of a module went to the far end of the course;
* deleting a module freed its lessons with their old numbers, and one
  appended late (it carries the course's highest number) jumped to the
  end;
* a new module took the modules' maximum plus one and landed in front of
  loose lessons the teacher had put at the end;
* the lock asked for "the chapter before" by lesson number alone, which
  is not the order the student is shown once a module's lessons were
  appended late.
"""

from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING, Any

from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.services.chapter_gate import chapter_is_open_to
from app.services.course_service._outline import live_spine
from app.services.course_structure import build_spine, number_outline, places_of
from tests.conftest import STUDENT_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

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
    """The course as it reads: module titles as ``[M]``, lessons by title."""
    db.expire_all()
    out: list[str] = []
    for run in live_spine(db, course_id).runs:
        if run.module is not None:
            out.append(f"[{run.module.id}]")
        out.extend(c.title for c in run.chapters)
    return out


def _outline(client: TestClient, course_id: str, places: list[tuple[str | None, list[str]]]) -> Any:
    return client.put(
        f"{PREFIX}/{course_id}/outline",
        json={"places": [{"module_id": m, "chapter_ids": ids} for m, ids in places]},
    )


# ─── The outline is written whole ───────────────────────────────────────


class TestTheOutlineIsWrittenWhole:
    def test_a_lesson_put_between_two_modules_stays_there(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        first = _module(client, course_id, "First")
        second = _module(client, course_id, "Second")
        a = _lesson(client, course_id, "a", first)
        b = _lesson(client, course_id, "b", second)
        loose = _lesson(client, course_id, "loose")

        saved = _outline(client, course_id, [(first, [a]), (None, [loose]), (second, [b])])

        assert saved.status_code == 204, saved.text
        assert _reads(db, course_id) == [f"[{first}]", "a", "loose", f"[{second}]", "b"]

    def test_moving_a_module_takes_its_lessons_and_leaves_the_loose_one(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        first = _module(client, course_id, "First")
        second = _module(client, course_id, "Second")
        a = _lesson(client, course_id, "a", first)
        b = _lesson(client, course_id, "b", second)
        loose = _lesson(client, course_id, "loose")
        assert _outline(client, course_id, [(first, [a]), (None, [loose]), (second, [b])]).status_code == 204

        assert _outline(client, course_id, [(second, [b]), (None, [loose]), (first, [a])]).status_code == 204

        assert _reads(db, course_id) == [f"[{second}]", "b", "loose", f"[{first}]", "a"]

    def test_a_lesson_can_be_filed_into_a_module_by_the_outline(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        module = _module(client, course_id, "M")
        loose = _lesson(client, course_id, "loose")

        assert _outline(client, course_id, [(module, [loose])]).status_code == 204

        db.expire_all()
        assert db.get(Chapter, loose).module_id == module

    def test_a_stale_outline_is_refused_and_writes_nothing(self, client: TestClient, db: Session) -> None:
        """A lesson added in another tab: the screen does not know it."""
        course_id = _course(client)
        module = _module(client, course_id, "M")
        a = _lesson(client, course_id, "a", module)
        _lesson(client, course_id, "added elsewhere")
        before = _reads(db, course_id)

        refused = _outline(client, course_id, [(None, [a]), (module, [])])

        assert refused.status_code == 409, refused.text
        assert _reads(db, course_id) == before

    def test_a_lesson_named_twice_or_from_another_course_is_refused(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        a = _lesson(client, course_id, "a")
        other = _lesson(client, _course(client), "elsewhere")

        assert _outline(client, course_id, [(None, [a]), (None, [a])]).status_code == 409
        assert _outline(client, course_id, [(None, [a, other])]).status_code == 409

    def test_only_the_owner_writes_it(self, db: Session, teacher: User, student_client: TestClient) -> None:
        course = Course(id=str(uuid.uuid4()), title="Course", created_by=teacher.id, source_locale="en")
        db.add(course)
        db.flush()
        lesson = Chapter(id=str(uuid.uuid4()), course_id=course.id, title="a", order_index=0)
        db.add(lesson)
        db.commit()

        assert _outline(student_client, course.id, [(None, [lesson.id])]).status_code == 403


# ─── The other writes keep the order too ────────────────────────────────


class TestEveryWriteKeepsThePlace:
    def test_a_lesson_taken_out_of_a_module_stays_right_after_it(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        first = _module(client, course_id, "First")
        second = _module(client, course_id, "Second")
        a1 = _lesson(client, course_id, "a1", first)
        _lesson(client, course_id, "a2", first)
        _lesson(client, course_id, "b1", second)

        moved = client.put(f"{PREFIX}/{course_id}/chapters/{a1}", json={"module_id": None})

        assert moved.status_code == 200, moved.text
        assert _reads(db, course_id) == [f"[{first}]", "a2", "a1", f"[{second}]", "b1"]

    def test_deleting_a_module_leaves_its_lessons_where_the_module_was(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        first = _module(client, course_id, "First")
        _lesson(client, course_id, "a1", first)
        loose = _lesson(client, course_id, "loose")
        second = _module(client, course_id, "Second")
        _lesson(client, course_id, "b1", second)
        # Appended to the first module last: the highest number in the course.
        _lesson(client, course_id, "a-late", first)
        assert _reads(db, course_id) == [f"[{first}]", "a1", "a-late", "loose", f"[{second}]", "b1"]
        assert loose

        removed = client.delete(f"{PREFIX}/{course_id}/modules/{first}")

        assert removed.status_code == 204, removed.text
        assert _reads(db, course_id) == ["a1", "a-late", "loose", f"[{second}]", "b1"]

    def test_a_new_module_goes_after_the_loose_lessons_at_the_end(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        _lesson(client, course_id, "one")
        _lesson(client, course_id, "two")

        module = _module(client, course_id, "Later")

        assert _reads(db, course_id) == ["one", "two", f"[{module}]"]

    def test_a_copy_of_the_course_reads_the_same(self, client: TestClient, db: Session) -> None:
        course_id = _course(client)
        first = _module(client, course_id, "First")
        a = _lesson(client, course_id, "a", first)
        loose = _lesson(client, course_id, "loose")
        second = _module(client, course_id, "Second")
        b = _lesson(client, course_id, "b", second)
        assert _outline(client, course_id, [(None, [loose]), (second, [b]), (first, [a])]).status_code == 204

        cloned = client.post(f"{PREFIX}/{course_id}/clone")
        assert cloned.status_code in (200, 201), cloned.text

        copy = [x for x in _reads(db, cloned.json()["id"]) if not x.startswith("[")]
        assert copy == ["loose", "b", "a"]


# ─── The lock walks the same sequence ───────────────────────────────────


def test_the_lock_waits_on_the_lesson_the_student_sees_before_it(db: Session, teacher: User, student: User) -> None:
    """A lesson appended to a module late carries the course's highest
    number. By number alone the lesson "before" it was the loose quiz
    after the module; the student sees the module's own quiz before it."""
    course = Course(
        id=str(uuid.uuid4()),
        title="Course",
        status="published",
        access_mode="public",
        created_by=teacher.id,
        source_locale="en",
    )
    db.add(course)
    db.flush()
    module = Module(id=str(uuid.uuid4()), course_id=course.id, title="M", order_index=0)
    db.add(module)
    db.flush()

    def lesson(title: str, order: int, kind: str, group: Module | None, *, locked: bool = False) -> Chapter:
        row = Chapter(
            id=str(uuid.uuid4()),
            course_id=course.id,
            module_id=group.id if group else None,
            title=title,
            order_index=order,
            chapter_type=kind,
            is_locked=locked,
        )
        db.add(row)
        db.flush()
        return row

    module_quiz = lesson("module quiz", 1, "quiz", module)
    lesson("loose quiz", 2, "quiz", None)
    late = lesson("late reading", 3, "reading", module, locked=True)
    db.add(Enrollment(id=str(uuid.uuid4()), user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.add(ChapterProgress(user_id=STUDENT_ID, chapter_id=module_quiz.id, completed=True))
    db.commit()

    assert [c.title for c in live_spine(db, course.id).chapters] == ["module quiz", "late reading", "loose quiz"]
    assert chapter_is_open_to(db, late, STUDENT_ID) is True


# ─── The numbering reads back as written ────────────────────────────────


def test_any_outline_numbered_reads_back_exactly() -> None:
    """``number_outline`` and ``build_spine`` are inverse: whatever the
    teacher arranges, the numbers read back as that arrangement."""
    rng = random.Random(20261016)
    for _ in range(200):
        modules = [Module(id=f"m{i}", course_id="c", title=f"m{i}", order_index=0) for i in range(rng.randint(0, 4))]
        lessons = [f"c{i}" for i in range(rng.randint(0, 8))]
        places: list[tuple[str | None, list[str]]] = [(m.id, []) for m in modules]
        for lesson_id in lessons:
            target = rng.randrange(len(places) + 1)
            if target == len(places) or places[target][0] is None:
                places.insert(rng.randint(0, len(places)), (None, [lesson_id]))
            else:
                places[target][1].append(lesson_id)

        numbers = number_outline(places)
        for module in modules:
            module.order_index = numbers.modules[module.id]
        chapters = [
            Chapter(id=cid, course_id="c", title=cid, module_id=mid, order_index=order)
            for cid, (order, mid) in numbers.chapters.items()
        ]
        rng.shuffle(chapters)
        rng.shuffle(modules)

        assert places_of(build_spine(modules, chapters)) == places
