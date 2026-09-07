"""A chapter belongs to its course, not only to its module.

``chapters.course_id`` arrived on 2026-09-07 (migration
``20260907173527_a_chapter_belongs_to_its_course``) as step 1 of letting a
module be an optional grouping instead of the only way to reach a chapter.
The step is additive, and these tests pin what "additive" means:

* every write path sets ``course_id`` itself, and it always equals the
  module's ``course_id`` — the invariant the later steps lean on;
* ``Course.chapters`` returns exactly what walking the modules returns;
* the backfill in the migration file fills the column from the module —
  run here, as the text production will run, against SQLite;
* the model declares exactly the indexes production has on ``chapters``.

The write-path tests switch the conftest autopopulator off (see
``chapters_name_their_own_course``): with it on, a path that forgot the
column would be quietly corrected and these tests would prove nothing.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.models.course import Chapter, Course, Module
from app.schemas.course import ChapterCreate
from app.services.course_service import clone_course, create_chapter, delete_chapter, get_course
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

# Every course here is owned by the seeded teacher; ``clone_course`` hands the
# copy to the same person.
pytestmark = pytest.mark.usefixtures("teacher")

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "supabase" / "migrations" / "20260907173527_a_chapter_belongs_to_its_course.sql"
SCHEMA_DUMP = REPO / "supabase" / "schema.sql"
PREFIX = "/api/v1/courses"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _course(db: Session, course_id: str = "c-owner") -> Course:
    course = Course(id=course_id, title="Course", created_by=TEACHER_ID, status="draft", source_locale="ru")
    db.add(course)
    db.commit()
    return course


def _module(db: Session, course_id: str, module_id: str, order_index: int = 0) -> Module:
    module = Module(id=module_id, course_id=course_id, title=f"Module {order_index + 1}", order_index=order_index)
    db.add(module)
    db.commit()
    return module


def _disagreements(db: Session) -> int:
    """Chapters whose course is not their module's course. Must be zero, always."""
    return (
        db.query(Chapter)
        .join(Module, Chapter.module_id == Module.id)
        .filter(Chapter.course_id != Module.course_id)
        .count()
    )


# ---------------------------------------------------------------------------
# Write paths set the column themselves
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("chapters_name_their_own_course")
def test_create_chapter_writes_the_course_of_its_module(db: Session):
    course = _course(db)
    module = _module(db, course.id, "m-1")

    chapter = create_chapter(db, module.id, ChapterCreate(title="Lesson 1"))

    assert chapter.course_id == course.id
    assert chapter.course_id == chapter.module.course_id
    assert chapter.course is course
    assert _disagreements(db) == 0


@pytest.mark.usefixtures("chapters_name_their_own_course")
def test_a_clone_puts_every_chapter_under_the_new_course(db: Session):
    course = _course(db)
    first = _module(db, course.id, "m-1", 0)
    second = _module(db, course.id, "m-2", 1)
    for module, titles in ((first, ("Lesson 1", "Lesson 2")), (second, ("Lesson 3",))):
        for title in titles:
            create_chapter(db, module.id, ChapterCreate(title=title))

    clone = clone_course(db, course.id, TEACHER_ID)

    assert clone is not None and clone.id != course.id
    cloned_chapters = [chapter for module in clone.modules for chapter in module.chapters]
    assert len(cloned_chapters) == 3
    assert {chapter.course_id for chapter in cloned_chapters} == {clone.id}
    assert all(chapter.course_id == chapter.module.course_id for chapter in cloned_chapters)
    assert _disagreements(db) == 0


@pytest.mark.usefixtures("chapters_name_their_own_course")
def test_the_response_names_the_course(client: TestClient):
    course_id = client.post(PREFIX, json={"title": "Four lessons"}).json()["id"]
    module_id = client.post(f"{PREFIX}/{course_id}/modules", json={"title": "Module 1"}).json()["id"]

    created = client.post(f"{PREFIX}/{course_id}/modules/{module_id}/chapters", json={"title": "Lesson 1"})

    assert created.status_code == 201, created.text
    assert created.json()["course_id"] == course_id
    assert created.json()["module_id"] == module_id

    tree = client.get(f"{PREFIX}/{course_id}").json()
    assert [chapter["course_id"] for module in tree["modules"] for chapter in module["chapters"]] == [course_id]


# ---------------------------------------------------------------------------
# The course reaches its chapters directly
# ---------------------------------------------------------------------------


def test_course_chapters_is_the_module_walk(db: Session):
    course = _course(db)
    first = _module(db, course.id, "m-1", 0)
    second = _module(db, course.id, "m-2", 1)
    # Out of order on purpose: the direct list must come back by ``order_index``.
    create_chapter(db, second.id, ChapterCreate(title="Lesson 3", order_index=7))
    create_chapter(db, first.id, ChapterCreate(title="Lesson 1", order_index=3))
    create_chapter(db, first.id, ChapterCreate(title="Lesson 2", order_index=5))
    binned = create_chapter(db, first.id, ChapterCreate(title="Binned", order_index=9))
    delete_chapter(db, binned)
    db.expire_all()

    loaded = get_course(db, course.id)

    assert loaded is not None
    via_modules = sorted(chapter.id for module in loaded.modules for chapter in module.chapters)
    direct = [chapter.id for chapter in loaded.chapters]
    assert sorted(direct) == via_modules
    assert binned.id not in direct
    assert [chapter.order_index for chapter in loaded.chapters] == [3, 5, 7]


# ---------------------------------------------------------------------------
# Test infrastructure: a builder that names only the module gets the course
# ---------------------------------------------------------------------------


def test_a_builder_that_names_only_the_module_gets_the_course(db: Session):
    course = _course(db)
    module = _module(db, course.id, "m-1")

    flat = Chapter(id="ch-flat", module_id=module.id, title="Flat")
    db.add(flat)
    db.commit()
    assert flat.course_id == course.id

    # Nested and all pending in one flush: the module's own FK is still
    # NULL when the listener runs, and it knows its course only by relationship.
    db.add(
        Course(
            id="c-nested",
            title="Nested",
            created_by=TEACHER_ID,
            modules=[Module(id="m-nested", title="Module", chapters=[Chapter(id="ch-nested", title="Nested")])],
        )
    )
    db.commit()
    nested = db.get(Chapter, "ch-nested")
    assert nested is not None
    assert nested.course_id == "c-nested"
    assert _disagreements(db) == 0


# ---------------------------------------------------------------------------
# The migration file itself
# ---------------------------------------------------------------------------


def _migration_statements_sqlite_can_run() -> list[str]:
    """The migration's statements, minus what SQLite has no words for.

    ``COMMENT ON`` and ``ALTER COLUMN … SET NOT NULL`` are dropped (the
    test asserts no NULL is left, which is what the latter would check);
    ``public.`` and ``ADD COLUMN IF NOT EXISTS`` are spelled the SQLite way.
    Everything else — the column with its FK, the ``UPDATE … FROM``
    backfill, the partial index — runs as written.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    sql = re.sub(r"COMMENT ON .*?';", "", sql, flags=re.S)
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    kept = [s for s in statements if "SET NOT NULL" not in s]
    return [s.replace("public.", "").replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN") for s in kept]


def test_the_backfill_fills_course_id_from_the_module():
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    # The three tables as production had them before the migration —
    # only what the statements touch.
    con.executescript(
        """
        CREATE TABLE courses (id TEXT PRIMARY KEY);
        CREATE TABLE modules (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id),
            deleted_at TEXT
        );
        CREATE TABLE chapters (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL REFERENCES modules(id),
            order_index INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT
        );
        INSERT INTO courses VALUES ('c-a'), ('c-b');
        INSERT INTO modules VALUES ('m-a1', 'c-a', NULL), ('m-a2', 'c-a', '2026-09-01'), ('m-b1', 'c-b', NULL);
        INSERT INTO chapters VALUES
            ('ch-1', 'm-a1', 0, NULL),
            ('ch-2', 'm-a1', 1, '2026-09-01'),
            ('ch-3', 'm-a2', 0, '2026-09-01'),
            ('ch-4', 'm-b1', 0, NULL);
        """
    )

    for statement in _migration_statements_sqlite_can_run():
        con.execute(statement)

    rows = con.execute(
        "SELECT c.id, c.course_id, m.course_id FROM chapters c JOIN modules m ON m.id = c.module_id ORDER BY c.id"
    ).fetchall()
    assert rows == [
        ("ch-1", "c-a", "c-a"),
        ("ch-2", "c-a", "c-a"),  # trashed chapters are backfilled too — NOT NULL must hold for every row
        ("ch-3", "c-a", "c-a"),  # …and chapters under a trashed module
        ("ch-4", "c-b", "c-b"),
    ]
    indexes = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "ix_chapters_course_id_order_active" in indexes


def test_the_migration_sets_the_column_not_null_after_the_backfill():
    """SQLite cannot run the ``SET NOT NULL``; pin its presence and its place instead."""
    sql = MIGRATION.read_text(encoding="utf-8")
    backfill = sql.index("UPDATE public.chapters")
    not_null = sql.index("ALTER COLUMN course_id SET NOT NULL")
    assert backfill < not_null


# ---------------------------------------------------------------------------
# The model mirrors production
# ---------------------------------------------------------------------------


def test_the_model_declares_exactly_the_indexes_production_has():
    dump = SCHEMA_DUMP.read_text(encoding="utf-8")

    declared = {index.name for index in Chapter.__table__.indexes}
    in_production = set(re.findall(r"CREATE INDEX (\w+) ON public\.chapters ", dump))
    assert declared == in_production == {"ix_chapters_module_id", "ix_chapters_course_id_order_active"}

    table = re.search(r"CREATE TABLE public\.chapters \((.*?)\n\);", dump, flags=re.S)
    assert table is not None
    assert "course_id character varying NOT NULL" in table.group(1)
    assert "chapters_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE" in dump
