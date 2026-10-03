# ruff: noqa: RUF001
# Russian course text on purpose: a Russian course being read in four
# languages is the case this is about.
"""New content on a live course is nobody's until it is released.

An *edit* to a published course waits in the staging table while readers
keep the old text. *New* content waits in the same table and has no old
text — and until 2026-10-03 it showed through: a new announcement listed
for students as an empty title over an empty body; a new chapter sat in
their tree under its spine title, opened as an empty lesson, and counted
as one more to read — or, for a quiz, against their progress and grade.

One rule now (``staged_edits.visibility``): content whose text has a held
human edit and no released row is awaiting its first release, and a reader
is not shown it or counted against it. The author, the owner and an admin
still see it, the way they already see their own held edits.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from app.api.consent_gate import consent_subject
from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.chapter_block import ChapterBlock
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.services.chapter_gate import chapter_is_open_to
from app.services.content_versions.write import record_human_version
from app.services.course_service import reading_progress_by_course
from app.services.course_service._enrollment import fresh_progress
from app.services.gradable_items import course_items
from app.services.grade_calculator import _get_course_chapter_ids
from app.services.staged_edits import promote_staged_entity_unconditionally, stage_human_edit
from tests._cv_helpers import make_quiz_with_text
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from app.models.user import User

API = "/api/v1"


@pytest.fixture
def c(db: Session) -> Iterator[TestClient]:
    def _db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user
    app.dependency_overrides[consent_subject] = lambda: user


def _ok(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, f"{r.request.method} {r.request.url}: {r.text}"
    return r.json()


def _live_course(db: Session, *, enrol: bool = True) -> tuple[str, str, str]:
    """A published Russian course with one module and one released lesson.

    Returns ``(course_id, module_id, chapter_id)``.
    """
    cid = f"live-{uuid.uuid4().hex[:6]}"
    course = Course(id=cid, status="published", source_locale="ru", created_by=TEACHER_ID, access_mode="public")
    module = Module(id=f"mod-{cid}", course_id=cid, order_index=0)
    db.add_all([course, module])
    db.flush()
    record_human_version(db, entity_type="course", entity_id=cid, field="title", locale="ru", text="Деяния")
    record_human_version(db, entity_type="module", entity_id=module.id, field="title", locale="ru", text="Начало")
    chapter_id = _released_chapter(db, cid, module.id, title="Пятидесятница", order_index=0)
    if enrol:
        db.add(Enrollment(id=f"enr-{cid}", user_id=STUDENT_ID, course_id=cid, progress=0))
    db.commit()
    return cid, module.id, chapter_id


def _released_chapter(
    db: Session, course_id: str, module_id: str, *, title: str, order_index: int, chapter_type: str = "reading"
) -> str:
    chapter = Chapter(
        id=f"ch-{uuid.uuid4().hex[:6]}",
        course_id=course_id,
        module_id=module_id,
        title=title,
        order_index=order_index,
        chapter_type=chapter_type,
    )
    db.add(chapter)
    db.flush()
    record_human_version(db, entity_type="chapter", entity_id=chapter.id, field="title", locale="ru", text=title)
    return chapter.id


def _held_chapter(
    db: Session, course_id: str, module_id: str, *, title: str, order_index: int, chapter_type: str = "reading"
) -> str:
    """What ``create_chapter`` leaves behind on a published course: the row,
    and its title held in the staging table rather than released."""
    chapter = Chapter(
        id=f"ch-{uuid.uuid4().hex[:6]}",
        course_id=course_id,
        module_id=module_id,
        title=title,
        order_index=order_index,
        chapter_type=chapter_type,
    )
    db.add(chapter)
    db.flush()
    stage_human_edit(
        db,
        entity_type="chapter",
        entity_id=chapter.id,
        course_id=course_id,
        field="title",
        locale="ru",
        text=title,
    )
    db.commit()
    return chapter.id


def _mark_read(db: Session, chapter_id: str) -> None:
    db.add(ChapterProgress(id=uuid.uuid4(), user_id=STUDENT_ID, chapter_id=chapter_id, completed=True))
    db.commit()


def _chapter_ids_in_tree(course: dict[str, Any]) -> set[str]:
    return {ch["id"] for module in course["modules"] for ch in module["chapters"]} | {
        ch["id"] for ch in course["chapters"]
    }


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------


def test_a_new_announcement_is_not_listed_for_students_until_it_is_released(
    c: TestClient, db: Session, teacher: User, student: User, admin: User
) -> None:
    cid, _module, _chapter = _live_course(db)
    _as(teacher)
    posted = _ok(
        c.post(
            f"{API}/announcements",
            json={"title": "Завтра занятия не будет", "content": "Переносим на четверг", "course_id": cid},
        ),
        201,
    )

    _as(student)
    assert _ok(c.get(f"{API}/announcements", params={"course_id": cid})) == []
    assert _ok(c.get(f"{API}/announcements")) == []

    # The author sees their own post — in the editor and in their feed.
    _as(teacher)
    assert [a["id"] for a in _ok(c.get(f"{API}/announcements", params={"course_id": cid, "source": 1}))] == [
        posted["id"]
    ]
    assert [a["id"] for a in _ok(c.get(f"{API}/announcements", params={"course_id": cid}))] == [posted["id"]]
    _as(admin)
    assert [a["id"] for a in _ok(c.get(f"{API}/announcements", params={"course_id": cid}))] == [posted["id"]]

    promote_staged_entity_unconditionally(db, course_id=cid)
    _as(student)
    (listed,) = _ok(c.get(f"{API}/announcements", params={"course_id": cid}))
    assert (listed["id"], listed["title"]) == (posted["id"], "Завтра занятия не будет")


def test_an_edit_to_a_released_announcement_keeps_it_listed(
    c: TestClient, db: Session, teacher: User, student: User
) -> None:
    """The second half of the predicate: a held edit to text that *has*
    been released is an ordinary edit in flight, shown with the old words."""
    cid, _module, _chapter = _live_course(db)
    _as(teacher)
    posted = _ok(c.post(f"{API}/announcements", json={"title": "Было", "content": "Текст", "course_id": cid}), 201)
    promote_staged_entity_unconditionally(db, course_id=cid)
    _ok(c.put(f"{API}/announcements/{posted['id']}", json={"title": "Стало"}))

    _as(student)
    (listed,) = _ok(c.get(f"{API}/announcements", params={"course_id": cid}))
    assert listed["title"] == "Было"


# ---------------------------------------------------------------------------
# Chapters and blocks
# ---------------------------------------------------------------------------


def test_a_new_chapter_is_not_in_the_students_tree_until_it_is_released(
    c: TestClient, db: Session, teacher: User, student: User
) -> None:
    cid, mid, released = _live_course(db)
    _as(teacher)
    created = _ok(
        c.post(
            f"{API}/courses/{cid}/modules/{mid}/chapters",
            json={"title": "Иерусалимский собор", "chapter_type": "reading", "order_index": 1},
        ),
        201,
    )
    # The owner sees the course as it will be.
    assert _chapter_ids_in_tree(_ok(c.get(f"{API}/courses/{cid}"))) == {released, created["id"]}

    _as(student)
    assert _chapter_ids_in_tree(_ok(c.get(f"{API}/courses/{cid}"))) == {released}
    module_view = _ok(c.get(f"{API}/courses/{cid}/modules/{mid}"))
    assert [ch["id"] for ch in module_view["chapters"]] == [released]

    promote_staged_entity_unconditionally(db, course_id=cid)
    assert _chapter_ids_in_tree(_ok(c.get(f"{API}/courses/{cid}"))) == {released, created["id"]}


def test_an_edit_to_a_released_chapter_keeps_it_in_the_tree(
    c: TestClient, db: Session, teacher: User, student: User
) -> None:
    cid, mid, released = _live_course(db)
    _as(teacher)
    _ok(c.put(f"{API}/courses/{cid}/modules/{mid}/chapters/{released}", json={"title": "Пятидесятница (ред.)"}))

    _as(student)
    tree = _ok(c.get(f"{API}/courses/{cid}"), 200)
    assert _chapter_ids_in_tree(tree) == {released}


def test_a_new_text_block_is_not_served_to_students_until_it_is_released(
    c: TestClient, db: Session, teacher: User, student: User
) -> None:
    cid, _mid, chapter = _live_course(db)
    _as(teacher)
    _ok(
        c.post(
            f"{API}/blocks/chapter/{chapter}",
            json={"block_type": "text", "order_index": 0, "content": "<p>В день Пятидесятницы</p>"},
        ),
        201,
    )
    # And a quiz block beside it, which carries no text to hold.
    quiz = make_quiz_with_text(db, chapter_id=chapter, title="Проверка", locale="ru")
    db.add(ChapterBlock(id=uuid.uuid4(), chapter_id=chapter, block_type="quiz", order_index=1, quiz_id=quiz.id))
    db.commit()
    editor = _ok(c.get(f"{API}/blocks/chapter/{chapter}", params={"source": 1}))
    assert [b["block_type"] for b in editor] == ["text", "quiz"]
    assert editor[0]["content"] == "<p>В день Пятидесятницы</p>"

    _as(student)
    assert [b["block_type"] for b in _ok(c.get(f"{API}/blocks/chapter/{chapter}"))] == ["quiz"]

    promote_staged_entity_unconditionally(db, course_id=cid)
    served = _ok(c.get(f"{API}/blocks/chapter/{chapter}"))
    assert [(b["block_type"], b["content"]) for b in served] == [
        ("text", "<p>В день Пятидесятницы</p>"),
        ("quiz", None),
    ]


# ---------------------------------------------------------------------------
# Denominators
# ---------------------------------------------------------------------------


def test_a_held_lesson_is_not_one_more_to_read(c: TestClient, db: Session, teacher: User, student: User) -> None:
    cid, mid, released = _live_course(db)
    _mark_read(db, released)
    assert reading_progress_by_course(db, STUDENT_ID, [cid])[cid] == (1, 1)

    _held_chapter(db, cid, mid, title="Новый урок", order_index=1)

    assert reading_progress_by_course(db, STUDENT_ID, [cid])[cid] == (1, 1)
    _as(student)
    (row,) = _ok(c.get(f"{API}/users/me/courses"))
    assert (row["chapters_read"], row["chapters_to_read"]) == (1, 1)

    promote_staged_entity_unconditionally(db, course_id=cid)
    assert reading_progress_by_course(db, STUDENT_ID, [cid])[cid] == (1, 2)


def test_a_held_quiz_does_not_count_against_progress_or_the_grade(db: Session, teacher: User, student: User) -> None:
    cid, mid, _reading = _live_course(db)
    passed = _released_chapter(db, cid, mid, title="Тест 1", order_index=1, chapter_type="quiz")
    make_quiz_with_text(db, chapter_id=passed, title="Тест 1", locale="ru")
    db.commit()
    _mark_read(db, passed)
    assert fresh_progress(db, STUDENT_ID, cid) == 100

    held = _held_chapter(db, cid, mid, title="Тест 2", order_index=2, chapter_type="quiz")
    make_quiz_with_text(db, chapter_id=held, title="Тест 2", locale="ru")
    db.commit()

    assert fresh_progress(db, STUDENT_ID, cid) == 100
    assert _get_course_chapter_ids(db, cid) == [passed]
    quizzes, _assignments = course_items(db, cid)
    assert [q.chapter_id for q in quizzes] == [passed]

    promote_staged_entity_unconditionally(db, course_id=cid)
    assert fresh_progress(db, STUDENT_ID, cid) == 50
    assert set(_get_course_chapter_ids(db, cid)) == {passed, held}


def test_a_held_quiz_keeps_reading_moving_a_course_with_nothing_else_to_assess(
    c: TestClient, db: Session, teacher: User, student: User
) -> None:
    cid, mid, released = _live_course(db)
    held = _held_chapter(db, cid, mid, title="Тест", order_index=1, chapter_type="quiz")
    make_quiz_with_text(db, chapter_id=held, title="Тест", locale="ru")
    db.commit()

    _as(student)
    _ok(c.put(f"{API}/progress/chapter/{released}/read"))

    assert _ok(c.get(f"{API}/grades/my/{cid}/breakdown"))["progress"] == 100


def test_a_locked_lesson_waits_on_the_last_lesson_students_can_see(db: Session, teacher: User, student: User) -> None:
    cid, mid, _reading = _live_course(db)
    passed = _released_chapter(db, cid, mid, title="Тест 1", order_index=1, chapter_type="quiz")
    _mark_read(db, passed)
    _held_chapter(db, cid, mid, title="Тест 2", order_index=2, chapter_type="quiz")
    locked_id = _released_chapter(db, cid, mid, title="Дальше", order_index=3)
    locked = db.get(Chapter, locked_id)
    assert locked is not None
    locked.is_locked = True
    db.commit()

    # The quiz before it, in the student's order, is the one they passed —
    # not the one nobody can open yet.
    assert chapter_is_open_to(db, locked, STUDENT_ID) is True
