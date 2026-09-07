"""A course is its chapters; a module is only a heading.

Step 4 of the chapter→course move, the half about what the teacher is
*told*: the readiness checklist, the progress board and the course card.
Every rule here started as a real course that could not go out —
the first teacher to build one on this product made four lessons, was
pushed by the checklist into inventing modules to hold them, deleted the
lessons, and was left with a course the same checklist called critically
broken because the modules he never wanted were empty.

Three things had to stop being true:

* **"the course has at least one module" was critical.** A course of
  lessons and no headings could never be published. It is now "the
  course has at least one chapter".
* **"this module has chapters" was critical.** An empty heading barred a
  publication. It is a remark.
* **the per-chapter checks walked modules.** A chapter outside every
  module was never looked at, so a course whose only reading was blank
  passed the gate with a clean checklist and shipped an empty page.

And two things had to start being true: a chapter with no module has to
reach the teacher's board (it used to key itself to the string
``"None"`` and drop off the matrix), and a card has to be able to say
how many lessons a course has instead of how many headings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.enrollment import Enrollment
from app.services.content_versions import record_human_version
from app.services.course_readiness import compute_readiness
from app.services.course_structure import UNGROUPED_GROUP_ID
from app.services.student_progress_service import (
    build_course_gradebook_matrix,
    build_course_student_progress,
    build_student_chapter_detail,
)
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User
    from app.services.course_readiness import ReadinessCheck, ReadinessReport

PREFIX = "/api/v1/courses"


# ─── Scene builders ─────────────────────────────────────────────────────


def _course(db: Session, *, title: str = "Course") -> Course:
    course = Course(
        id=str(uuid.uuid4()),
        title=title,
        description="A description, so the catalog checks are not the noise.",
        image_url="https://example.org/cover.png",
        status=CourseStatus.DRAFT,
        access_mode="public",
        created_by=TEACHER_ID,
        source_locale="en",
    )
    db.add(course)
    db.flush()
    return course


def _module(db: Session, course: Course, *, title: str = "Module", order: int = 0) -> Module:
    module = Module(id=str(uuid.uuid4()), course_id=course.id, title=title, order_index=order)
    db.add(module)
    db.flush()
    return module


def _chapter(
    db: Session,
    course: Course,
    *,
    module: Module | None = None,
    title: str = "Lesson",
    order: int = 0,
    chapter_id: str | None = None,
) -> Chapter:
    """A chapter of ``course``. ``module=None`` is the whole point: the
    chapter names its course and no heading at all."""
    chapter = Chapter(
        id=chapter_id or str(uuid.uuid4()),
        course_id=course.id,
        module_id=module.id if module is not None else None,
        title=title,
        chapter_type="reading",
        order_index=order,
    )
    db.add(chapter)
    db.flush()
    return chapter


def _with_reading(db: Session, chapter: Chapter, *, text: str = "In the beginning…") -> Chapter:
    block = ChapterBlock(chapter_id=chapter.id, block_type="text", order_index=0)
    db.add(block)
    db.flush()
    record_human_version(
        db,
        entity_type="chapter_block",
        entity_id=str(block.id),
        field="content",
        locale="en",
        text=text,
    )
    return chapter


def _enroll(db: Session, course: Course) -> None:
    db.add(Enrollment(id=str(uuid.uuid4()), user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.flush()


def _check(report: ReadinessReport, prefix: str) -> ReadinessCheck | None:
    return next((c for c in report.checks if c.id.startswith(prefix)), None)


def _checks(report: ReadinessReport, prefix: str) -> list[ReadinessCheck]:
    return [c for c in report.checks if c.id.startswith(prefix)]


# ─── Readiness ──────────────────────────────────────────────────────────


def test_a_course_of_only_chapters_is_ready(db: Session, teacher: User):
    """Four lessons, no module. Nothing critical is missing."""
    course = _course(db)
    for i in range(4):
        _with_reading(db, _chapter(db, course, title=f"Lesson {i}", order=i))

    report = compute_readiness(db, course)

    structural = _check(report, "has_at_least_one_chapter")
    assert structural is not None
    assert structural.passed is True
    assert structural.severity == "critical"
    assert report.critical_failing == 0
    # The old blocker is gone entirely, not merely passing.
    assert _check(report, "has_at_least_one_module") is None


def test_a_course_with_no_chapters_at_all_is_not_ready(db: Session, teacher: User):
    """The rule that replaced "has a module" still bars the empty course:
    a heading with nothing under it is not a course."""
    course = _course(db)
    _module(db, course)

    report = compute_readiness(db, course)

    structural = _check(report, "has_at_least_one_chapter")
    assert structural is not None
    assert structural.passed is False
    assert structural.severity == "critical"


def test_an_empty_module_is_a_remark_not_a_bar(db: Session, teacher: User):
    """The live teacher's course, exactly: four modules, three of them
    empty, one lesson between them. It publishes."""
    course = _course(db)
    modules = [_module(db, course, title=f"Module {i}", order=i) for i in range(4)]
    _with_reading(db, _chapter(db, course, module=modules[0], title="The only lesson"))

    report = compute_readiness(db, course)

    empties = [c for c in _checks(report, "module_has_chapters:") if not c.passed]
    assert len(empties) == 3
    assert {c.severity for c in empties} == {"polish"}
    assert report.critical_failing == 0


def test_one_module_alone_is_not_remarked_on_in_a_course_without_modules(db: Session, teacher: User):
    """ "The course has only one module" is not something to say to a
    teacher who chose to have none."""
    course = _course(db)
    _with_reading(db, _chapter(db, course))

    assert _check(compute_readiness(db, course), "has_multiple_modules") is None

    grouped = _course(db, title="Grouped")
    _with_reading(db, _chapter(db, grouped, module=_module(db, grouped)))

    remark = _check(compute_readiness(db, grouped), "has_multiple_modules")
    assert remark is not None
    assert remark.severity == "polish"
    assert remark.passed is False


def test_a_chapter_outside_a_module_is_checked_like_any_other(db: Session, teacher: User):
    """The gate the loose chapter used to walk straight through. Its
    reading is blank; the checklist has to say so."""
    course = _course(db)
    grouped = _with_reading(db, _chapter(db, course, module=_module(db, course), title="Grouped"))
    loose = _chapter(db, course, title="Loose", order=1)
    _with_reading(db, loose, text="   ")  # whitespace only — the same as empty

    report = compute_readiness(db, course)

    assert _check(report, f"reading_has_content:{grouped.id}") is not None
    loose_check = _check(report, f"reading_has_content:{loose.id}")
    assert loose_check is not None
    assert loose_check.passed is False
    assert loose_check.severity == "critical"
    assert report.critical_failing == 1


def test_every_chapter_is_checked_exactly_once(db: Session, teacher: User):
    """Walking the course rather than the modules must not double-count
    the chapters that do have one."""
    course = _course(db)
    module = _module(db, course)
    grouped = _with_reading(db, _chapter(db, course, module=module, title="Grouped"))
    loose = _with_reading(db, _chapter(db, course, title="Loose", order=1))

    report = compute_readiness(db, course)
    reading_checks = [c.id for c in _checks(report, "reading_has_content:")]

    assert sorted(reading_checks) == sorted([f"reading_has_content:{grouped.id}", f"reading_has_content:{loose.id}"])


def test_a_course_of_only_chapters_publishes(db: Session, client: TestClient):
    """End to end, over the wire: the checklist the editor reads has
    nothing critical to say, and the course goes out."""
    course = _course(db)
    for i in range(4):
        _with_reading(db, _chapter(db, course, title=f"Lesson {i}", order=i))
    db.commit()

    assert client.get(f"{PREFIX}/{course.id}/readiness").json()["critical_failing"] == 0

    response = client.put(f"{PREFIX}/{course.id}", json={"status": "published"})

    assert response.status_code == 200
    assert response.json()["status"] == CourseStatus.PUBLISHED.value


def test_a_course_with_an_empty_module_publishes(db: Session, client: TestClient):
    """The live teacher's course over the wire. The empty headings are in
    the checklist as remarks and nothing is in the way of publishing."""
    course = _course(db)
    modules = [_module(db, course, title=f"Module {i}", order=i) for i in range(4)]
    _with_reading(db, _chapter(db, course, module=modules[0], title="The only lesson"))
    db.commit()

    checklist = client.get(f"{PREFIX}/{course.id}/readiness").json()
    empties = [c for c in checklist["checks"] if c["id"].startswith("module_has_chapters:") and not c["passed"]]

    assert checklist["critical_failing"] == 0
    assert [c["severity"] for c in empties] == ["polish"] * 3

    response = client.put(f"{PREFIX}/{course.id}", json={"status": "published"})

    assert response.status_code == 200
    assert response.json()["status"] == CourseStatus.PUBLISHED.value


# ─── The teacher's reports ──────────────────────────────────────────────


def test_the_board_carries_a_group_for_the_chapters_with_no_module(db: Session, teacher: User, student: User):
    course = _course(db)
    module = _module(db, course, title="Part one")
    grouped = _chapter(db, course, module=module, title="Grouped")
    loose = _chapter(db, course, title="Loose", order=1)
    _enroll(db, course)

    board = build_course_student_progress(db, course, course.id)
    groups = {g["id"]: g for g in board["modules"]}

    assert set(groups) == {module.id, UNGROUPED_GROUP_ID}
    assert groups[module.id]["is_ungrouped"] is False
    assert groups[UNGROUPED_GROUP_ID]["is_ungrouped"] is True
    # Ordered past the last module, so the client's existing sort puts the
    # loose lessons at the end rather than in front of the course.
    assert groups[UNGROUPED_GROUP_ID]["order_index"] > groups[module.id]["order_index"]

    matrix = build_course_gradebook_matrix(db, course, course.id)
    keyed = [ch["module_id"] for student in matrix["students"] for ch in student["chapters"]]
    by_chapter = {ch["id"]: ch["module_id"] for student in matrix["students"] for ch in student["chapters"]}

    # Every chapter is in the matrix once, and every one of them names a
    # group the payload actually describes — "None" named nothing.
    assert len(keyed) == 2
    assert by_chapter == {grouped.id: module.id, loose.id: UNGROUPED_GROUP_ID}
    assert set(keyed) <= set(groups)


def test_a_course_with_no_modules_reports_one_group(db: Session, teacher: User, student: User):
    course = _course(db)
    chapters = [_chapter(db, course, title=f"Lesson {i}", order=i) for i in range(4)]
    _enroll(db, course)

    board = build_course_student_progress(db, course, course.id)
    detail = build_student_chapter_detail(db, course, course.id, str(STUDENT_ID))

    assert [g["id"] for g in board["modules"]] == [UNGROUPED_GROUP_ID]
    assert [ch["id"] for ch in detail["chapters"]] == [c.id for c in chapters]
    assert {ch["module_id"] for ch in detail["chapters"]} == {UNGROUPED_GROUP_ID}


def test_a_course_without_loose_chapters_grows_no_extra_group(db: Session, teacher: User, student: User):
    course = _course(db)
    module = _module(db, course)
    _chapter(db, course, module=module)
    _enroll(db, course)

    board = build_course_student_progress(db, course, course.id)

    assert [g["id"] for g in board["modules"]] == [module.id]


def test_the_groups_chapters_run_consecutively(db: Session, teacher: User, student: User):
    """Course-global order, each heading's lessons together, the loose
    ones as one group at the tail."""
    course = _course(db)
    one = _module(db, course, title="One", order=0)
    two = _module(db, course, title="Two", order=1)
    _chapter(db, course, module=two, title="two-a", order=0, chapter_id="two-a")
    _chapter(db, course, title="loose-b", order=1, chapter_id="loose-b")
    _chapter(db, course, module=one, title="one-b", order=1, chapter_id="one-b")
    _chapter(db, course, title="loose-a", order=0, chapter_id="loose-a")
    _chapter(db, course, module=one, title="one-a", order=0, chapter_id="one-a")
    _enroll(db, course)

    detail = build_student_chapter_detail(db, course, course.id, str(STUDENT_ID))

    assert [ch["id"] for ch in detail["chapters"]] == ["one-a", "one-b", "two-a", "loose-a", "loose-b"]


def test_a_lesson_written_straight_into_the_course_arrives_everywhere(db: Session, client: TestClient, student: User):
    """The seam with the routes that write a lesson into a course.

    Those number a new chapter from the course-global maximum; this file
    decides how the result is *read*. One rule, not two: modules by
    ``module.order_index``, chapters by ``order_index`` inside each, and
    the ones with no module as a group at the tail. A lesson posted to
    the course has to reach the checklist, the board and the card without
    anyone here knowing which route made it.
    """
    created = client.post(f"{PREFIX}", json={"title": "Written straight in", "description": "…"})
    assert created.status_code == 201, created.text
    course_id = created.json()["id"]

    module_id = client.post(f"{PREFIX}/{course_id}/modules", json={"title": "Part one"}).json()["id"]
    grouped = client.post(f"{PREFIX}/{course_id}/modules/{module_id}/chapters", json={"title": "Grouped"}).json()
    loose = client.post(f"{PREFIX}/{course_id}/chapters", json={"title": "Loose"}).json()

    # The tree's two lists are a partition; the count is the whole of it,
    # taken in SQL rather than by summing the two and hoping.
    tree = client.get(f"{PREFIX}/{course_id}").json()
    assert [c["id"] for m in tree["modules"] for c in m["chapters"]] == [grouped["id"]]
    assert [c["id"] for c in tree["chapters"]] == [loose["id"]]

    listed = {c["id"]: c for c in client.get(f"{PREFIX}/my").json()}
    assert listed[course_id]["chapter_count"] == 2
    assert listed[course_id]["module_count"] == 1

    checklist = client.get(f"{PREFIX}/{course_id}/readiness").json()
    readings = [c["id"] for c in checklist["checks"] if c["id"].startswith("reading_has_content:")]
    assert sorted(readings) == sorted([f"reading_has_content:{grouped['id']}", f"reading_has_content:{loose['id']}"])

    course = db.query(Course).filter(Course.id == course_id).one()
    _enroll(db, course)
    db.commit()
    detail = build_student_chapter_detail(db, course, course_id, str(STUDENT_ID))

    assert [(ch["id"], ch["module_id"]) for ch in detail["chapters"]] == [
        (grouped["id"], module_id),
        (loose["id"], UNGROUPED_GROUP_ID),
    ]


def test_a_lesson_moved_out_of_its_module_joins_the_loose_group(db: Session, client: TestClient, student: User):
    """A regrouped lesson goes to the end of the course. The board has to
    put it in the group at the end of the course too, not leave it keyed
    to the heading it just left."""
    created = client.post(f"{PREFIX}", json={"title": "Regrouped", "description": "…"})
    course_id = created.json()["id"]
    module_id = client.post(f"{PREFIX}/{course_id}/modules", json={"title": "Part one"}).json()["id"]
    stays = client.post(f"{PREFIX}/{course_id}/modules/{module_id}/chapters", json={"title": "Stays"}).json()
    leaves = client.post(f"{PREFIX}/{course_id}/modules/{module_id}/chapters", json={"title": "Leaves"}).json()

    moved = client.put(f"{PREFIX}/{course_id}/chapters/{leaves['id']}", json={"module_id": None})
    assert moved.status_code == 200, moved.text
    assert moved.json()["module_id"] is None

    course = db.query(Course).filter(Course.id == course_id).one()
    _enroll(db, course)
    db.commit()
    detail = build_student_chapter_detail(db, course, course_id, str(STUDENT_ID))

    assert [(ch["id"], ch["module_id"]) for ch in detail["chapters"]] == [
        (stays["id"], module_id),
        (leaves["id"], UNGROUPED_GROUP_ID),
    ]
    assert client.get(f"{PREFIX}/{course_id}/readiness").json()["critical_failing"] == 2  # both readings are blank


# ─── The card ───────────────────────────────────────────────────────────


def test_the_card_counts_lessons_not_only_headings(db: Session, client: TestClient):
    """Three shapes of course, one list request. The chapters-only course
    is the one the old card called empty."""
    modules_only = _course(db, title="Headings only")
    for i in range(3):
        _module(db, modules_only, title=f"Module {i}", order=i)

    chapters_only = _course(db, title="Lessons only")
    for i in range(4):
        _chapter(db, chapters_only, title=f"Lesson {i}", order=i)

    mixed = _course(db, title="Both")
    mixed_module = _module(db, mixed, title="Part one")
    _chapter(db, mixed, module=mixed_module, title="Grouped")
    _chapter(db, mixed, title="Loose", order=1)
    db.commit()

    listed = {c["title"]: c for c in client.get(f"{PREFIX}/my").json()}

    assert (listed["Headings only"]["chapter_count"], listed["Headings only"]["module_count"]) == (0, 3)
    assert (listed["Lessons only"]["chapter_count"], listed["Lessons only"]["module_count"]) == (4, 0)
    assert (listed["Both"]["chapter_count"], listed["Both"]["module_count"]) == (2, 1)
    # The old field is still there and still says what it always said, so
    # nothing breaks before the frontend moves across.
    assert len(listed["Headings only"]["modules"]) == 3


def test_the_count_leaves_out_binned_lessons(db: Session, client: TestClient):
    course = _course(db, title="With a bin")
    _chapter(db, course, title="Kept")
    binned = _chapter(db, course, title="Binned", order=1)
    binned.deleted_at = datetime.now(UTC)
    db.commit()

    listed = {c["title"]: c for c in client.get(f"{PREFIX}/my").json()}

    assert listed["With a bin"]["chapter_count"] == 1
