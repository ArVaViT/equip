"""A lesson can be written straight into the course, with no module.

Step 4 of the chapter→course move: the routes. Steps 1-3 made a chapter
name its own course, taught every reader to reach it that way, and let
``chapters.module_id`` be NULL — so a lesson without a module became
legal in the database while remaining impossible to create through the
API. These tests pin the shape that closes that gap:

* ``POST /courses/{c}/chapters`` writes a lesson into the course itself,
  and ``GET /courses/{c}`` shows it — the failure mode being a lesson
  that exists, is graded, counts toward a denominator, and appears
  nowhere;
* the course response is a partition, not a duplication: a grouped
  lesson is in ``modules[].chapters`` and a loose one is in
  ``chapters``, and neither list repeats the other's rows;
* a lesson moves between the two by ``PUT`` with ``module_id``, and only
  ever within its own course;
* ``GET /courses/{c}/chapters/{id}`` answers for one lesson, which no
  endpoint could do before — the web app was fetching the whole module
  to read a chapter out of it, and that cannot work for a chapter with
  no module;
* ``order_index`` is course-global, so a loose lesson has somewhere
  to go and a grouped one still lands at the tail of its group.

The teacher who prompted all this had four lessons, no use for a module,
invented one anyway, recut the structure twice and deleted the lessons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from app.models.course import Chapter, Course

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

PREFIX = "/api/v1/courses"

# ---------------------------------------------------------------------------
# Builders — through the routes, because the routes are what is on trial
# ---------------------------------------------------------------------------


def _course(client: TestClient, title: str = "Course") -> str:
    created = client.post(PREFIX, json={"title": title})
    assert created.status_code == 201, created.text
    course_id: str = created.json()["id"]
    return course_id


def _module(client: TestClient, course_id: str, title: str = "Module") -> str:
    created = client.post(f"{PREFIX}/{course_id}/modules", json={"title": title})
    assert created.status_code == 201, created.text
    module_id: str = created.json()["id"]
    return module_id


def _in_module(client: TestClient, course_id: str, module_id: str, title: str, **extra: Any) -> dict[str, Any]:
    created = client.post(f"{PREFIX}/{course_id}/modules/{module_id}/chapters", json={"title": title, **extra})
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def _in_course(client: TestClient, course_id: str, title: str, **extra: Any) -> dict[str, Any]:
    created = client.post(f"{PREFIX}/{course_id}/chapters", json={"title": title, **extra})
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def _tree(client: TestClient, course_id: str, *, source: bool = False) -> dict[str, Any]:
    url = f"{PREFIX}/{course_id}?source=1" if source else f"{PREFIX}/{course_id}"
    fetched = client.get(url)
    assert fetched.status_code == 200, fetched.text
    body: dict[str, Any] = fetched.json()
    return body


def _grouped_ids(tree: dict[str, Any]) -> list[str]:
    return [chapter["id"] for module in tree["modules"] for chapter in module["chapters"]]


def _loose_ids(tree: dict[str, Any]) -> list[str]:
    return [chapter["id"] for chapter in tree["chapters"]]


# ---------------------------------------------------------------------------
# A course of four lessons
# ---------------------------------------------------------------------------


def test_a_course_of_four_lessons_needs_no_module(client: TestClient):
    course_id = _course(client, "Four lessons")

    created = [_in_course(client, course_id, f"Lesson {n}") for n in range(1, 5)]

    assert [chapter["module_id"] for chapter in created] == [None, None, None, None]
    assert {chapter["course_id"] for chapter in created} == {course_id}

    tree = _tree(client, course_id)
    assert tree["modules"] == []
    assert [chapter["title"] for chapter in tree["chapters"]] == ["Lesson 1", "Lesson 2", "Lesson 3", "Lesson 4"]


def test_a_loose_lesson_reaches_a_course_that_also_has_modules(client: TestClient):
    course_id = _course(client)
    module_id = _module(client, course_id)
    grouped = _in_module(client, course_id, module_id, "Grouped")
    loose = _in_course(client, course_id, "Loose")

    tree = _tree(client, course_id)

    assert _grouped_ids(tree) == [grouped["id"]]
    assert _loose_ids(tree) == [loose["id"]]


# ---------------------------------------------------------------------------
# The two lists are a partition — nobody can count a lesson twice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", [False, True])
def test_the_course_response_never_carries_a_lesson_twice(client: TestClient, source: bool):
    """``modules[].chapters`` and ``chapters`` never overlap.

    Both branches of ``GET /courses/{id}`` are checked. The ``?source=1``
    one is the one that would break by accident: it serialises the ORM
    row whole, and ``Course.chapters`` is *every* chapter of the course,
    grouped ones included.
    """
    course_id = _course(client)
    first = _module(client, course_id, "Module 1")
    second = _module(client, course_id, "Module 2")
    grouped = [
        _in_module(client, course_id, first, "Lesson 1")["id"],
        _in_module(client, course_id, first, "Lesson 2")["id"],
        _in_module(client, course_id, second, "Lesson 3")["id"],
    ]
    loose = [_in_course(client, course_id, "Lesson 4")["id"]]

    tree = _tree(client, course_id, source=source)

    assert sorted(_grouped_ids(tree)) == sorted(grouped)
    assert _loose_ids(tree) == loose
    everything = _grouped_ids(tree) + _loose_ids(tree)
    assert len(everything) == len(set(everything)) == 4


# ---------------------------------------------------------------------------
# Moving between the group and the course
# ---------------------------------------------------------------------------


def test_a_lesson_can_leave_its_module_and_come_back(client: TestClient):
    course_id = _course(client)
    module_id = _module(client, course_id)
    chapter_id = _in_module(client, course_id, module_id, "Lesson 1")["id"]

    out = client.put(f"{PREFIX}/{course_id}/chapters/{chapter_id}", json={"module_id": None})
    assert out.status_code == 200, out.text
    assert out.json()["module_id"] is None
    assert out.json()["course_id"] == course_id

    tree = _tree(client, course_id)
    assert _grouped_ids(tree) == []
    assert _loose_ids(tree) == [chapter_id]

    back = client.put(f"{PREFIX}/{course_id}/chapters/{chapter_id}", json={"module_id": module_id})
    assert back.status_code == 200, back.text
    assert back.json()["module_id"] == module_id

    tree = _tree(client, course_id)
    assert _grouped_ids(tree) == [chapter_id]
    assert _loose_ids(tree) == []


def test_a_body_without_module_id_leaves_the_grouping_alone(client: TestClient):
    """``exclude_unset`` is what separates "no module" from "not mentioned"."""
    course_id = _course(client)
    module_id = _module(client, course_id)
    chapter_id = _in_module(client, course_id, module_id, "Lesson 1")["id"]

    renamed = client.put(f"{PREFIX}/{course_id}/chapters/{chapter_id}", json={"title": "Lesson one"})

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Lesson one"
    assert renamed.json()["module_id"] == module_id


def test_a_lesson_cannot_be_moved_into_another_courses_module(client: TestClient):
    """The teacher owns both courses, and it is still refused.

    Ownership is not the point — the chapter's ``course_id`` is. A
    chapter grouped under a module of another course would disagree with
    its own course, and every read since step 2 trusts that they agree.
    """
    mine = _course(client, "Mine")
    my_module = _module(client, mine, "Module 1")
    chapter_id = _in_module(client, mine, my_module, "Lesson 1")["id"]

    elsewhere = _course(client, "Elsewhere")
    other_module = _module(client, elsewhere, "Module 1")

    refused = client.put(f"{PREFIX}/{mine}/chapters/{chapter_id}", json={"module_id": other_module})

    assert refused.status_code == 404, refused.text
    assert refused.json()["detail"]["code"] == "resource.not_found"
    assert refused.json()["detail"]["context"]["resource_type"] == "module"
    # And the lesson is exactly where it was.
    assert _grouped_ids(_tree(client, mine)) == [chapter_id]
    assert _grouped_ids(_tree(client, elsewhere)) == []


def test_a_module_that_does_not_exist_is_refused_too(client: TestClient):
    course_id = _course(client)
    module_id = _module(client, course_id)
    chapter_id = _in_module(client, course_id, module_id, "Lesson 1")["id"]

    refused = client.put(f"{PREFIX}/{course_id}/chapters/{chapter_id}", json={"module_id": "no-such-module"})

    assert refused.status_code == 404, refused.text
    assert refused.json()["detail"]["code"] == "resource.not_found"


def test_the_module_scoped_route_moves_a_lesson_out_as_well(client: TestClient):
    """The old URL keeps working, including for the new field."""
    course_id = _course(client)
    module_id = _module(client, course_id)
    chapter_id = _in_module(client, course_id, module_id, "Lesson 1")["id"]

    out = client.put(
        f"{PREFIX}/{course_id}/modules/{module_id}/chapters/{chapter_id}",
        json={"module_id": None},
    )

    assert out.status_code == 200, out.text
    assert out.json()["module_id"] is None
    assert _loose_ids(_tree(client, course_id)) == [chapter_id]


# ---------------------------------------------------------------------------
# One lesson, by its id
# ---------------------------------------------------------------------------


def test_a_lesson_is_fetched_by_its_own_id(client: TestClient):
    course_id = _course(client)
    module_id = _module(client, course_id)
    grouped = _in_module(client, course_id, module_id, "Grouped")
    loose = _in_course(client, course_id, "Loose")

    for expected in (grouped, loose):
        fetched = client.get(f"{PREFIX}/{course_id}/chapters/{expected['id']}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json() == expected


def test_a_lesson_of_another_course_is_not_found_here(client: TestClient):
    """Same owner, wrong course in the path. The path is the scope."""
    mine = _course(client, "Mine")
    module_id = _module(client, mine, "Module 1")
    chapter_id = _in_module(client, mine, module_id, "Lesson 1")["id"]
    elsewhere = _course(client, "Elsewhere")

    fetched = client.get(f"{PREFIX}/{elsewhere}/chapters/{chapter_id}")

    assert fetched.status_code == 404, fetched.text
    assert fetched.json()["detail"]["code"] == "resource.not_found"


def test_a_lesson_in_somebody_elses_course_is_refused(client: TestClient, db: Session, student: User):
    """Somebody else owns the course. The chapter is real and still not theirs."""
    course = Course(id="c-stranger", title="Not yours", created_by=student.id, status="draft", source_locale="ru")
    db.add(course)
    db.commit()
    db.add(Chapter(id="ch-stranger", course_id=course.id, module_id=None, title="Lesson 1", order_index=0))
    db.commit()

    fetched = client.get(f"{PREFIX}/{course.id}/chapters/ch-stranger")

    assert fetched.status_code == 403, fetched.text
    assert fetched.json()["detail"]["code"] == "auth.forbidden"


def test_a_lesson_that_does_not_exist_is_a_404(client: TestClient):
    course_id = _course(client)

    fetched = client.get(f"{PREFIX}/{course_id}/chapters/no-such-chapter")

    assert fetched.status_code == 404, fetched.text
    assert fetched.json()["detail"]["code"] == "resource.not_found"


def test_a_loose_lesson_is_deleted_through_the_course(client: TestClient):
    course_id = _course(client)
    chapter_id = _in_course(client, course_id, "Lesson 1")["id"]

    removed = client.delete(f"{PREFIX}/{course_id}/chapters/{chapter_id}")

    assert removed.status_code == 204, removed.text
    assert _loose_ids(_tree(client, course_id)) == []
    assert client.get(f"{PREFIX}/{course_id}/chapters/{chapter_id}").status_code == 404


# ---------------------------------------------------------------------------
# Order — course-global, and the modules keep the order they showed
# ---------------------------------------------------------------------------


def test_a_new_lesson_lands_after_everything_the_course_has(client: TestClient):
    course_id = _course(client)
    module_id = _module(client, course_id)

    first = _in_module(client, course_id, module_id, "Lesson 1")
    second = _in_module(client, course_id, module_id, "Lesson 2")
    loose = _in_course(client, course_id, "Lesson 3")
    third = _in_module(client, course_id, module_id, "Lesson 4")

    assert [row["order_index"] for row in (first, second, loose, third)] == [0, 1, 2, 3]


def test_a_lesson_appended_to_a_module_still_shows_last_in_it(client: TestClient):
    """The numbers change; the order on screen does not.

    Two modules filled alternately. Under the old per-module maximum the
    second module's chapters were numbered 0, 1; under the course-global
    one they are 1, 3. Either way each module lists its own lessons in
    the order they were added, which is all a reader ever saw.
    """
    course_id = _course(client)
    first = _module(client, course_id, "Module 1")
    second = _module(client, course_id, "Module 2")

    added = [
        _in_module(client, course_id, first, "One")["id"],
        _in_module(client, course_id, second, "Two")["id"],
        _in_module(client, course_id, first, "Three")["id"],
        _in_module(client, course_id, second, "Four")["id"],
    ]

    tree = _tree(client, course_id)
    by_module = {module["id"]: [chapter["id"] for chapter in module["chapters"]] for module in tree["modules"]}
    assert by_module[first] == [added[0], added[2]]
    assert by_module[second] == [added[1], added[3]]


def test_a_regrouped_lesson_goes_to_the_end_of_the_course(client: TestClient):
    """Otherwise it would collide with a number the new group already uses.

    Two chapters sharing an ``order_index`` inside one module are shown
    in whichever order the query plan chose — the defect the explicit
    ``order_by`` was added to stop.
    """
    course_id = _course(client)
    first = _module(client, course_id, "Module 1")
    second = _module(client, course_id, "Module 2")
    moving = _in_module(client, course_id, first, "Moving")
    _in_module(client, course_id, second, "Stays")
    assert moving["order_index"] == 0

    moved = client.put(f"{PREFIX}/{course_id}/chapters/{moving['id']}", json={"module_id": second})

    assert moved.status_code == 200, moved.text
    assert moved.json()["order_index"] == 2
    assert [chapter["title"] for module in _tree(client, course_id)["modules"] for chapter in module["chapters"]] == [
        "Stays",
        "Moving",
    ]


def test_a_move_that_names_an_order_keeps_the_one_it_was_given(client: TestClient):
    course_id = _course(client)
    first = _module(client, course_id, "Module 1")
    second = _module(client, course_id, "Module 2")
    moving = _in_module(client, course_id, first, "Moving")
    _in_module(client, course_id, second, "Stays")

    moved = client.put(
        f"{PREFIX}/{course_id}/chapters/{moving['id']}",
        json={"module_id": second, "order_index": 7},
    )

    assert moved.status_code == 200, moved.text
    assert moved.json()["order_index"] == 7


def test_an_order_that_is_not_moving_anywhere_is_left_alone(client: TestClient):
    """A patch naming the module the lesson is already in is not a move."""
    course_id = _course(client)
    module_id = _module(client, course_id)
    first = _in_module(client, course_id, module_id, "One")
    second = _in_module(client, course_id, module_id, "Two")
    assert second["order_index"] == 1

    unmoved = client.put(f"{PREFIX}/{course_id}/chapters/{first['id']}", json={"module_id": module_id})

    assert unmoved.status_code == 200, unmoved.text
    assert unmoved.json()["order_index"] == 0
