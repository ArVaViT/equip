"""One order for the course, read the same way by every surface.

The rule (``course_structure``, 2026-10-16): a module and a lesson that
sits in no module each take a place in one sequence, numbered in one
shared space by their own ``order_index``; a module's lessons run
consecutively under it, ordered by their own numbers, which are never
compared with anything outside the module.

History: before 2026-10-16 a loose lesson was placed by comparing its
number with the number of the first lesson of each module, and modules
were ordered by a number of their own in a different space. The board,
the PDF and the checklist read that; the student's and the teacher's
screens swept loose lessons to the tail. Reordering a module's lessons
could carry a loose lesson past the module, and an empty module could
not stand after a loose lesson at all. The tests below pin the one rule.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.enrollment import Enrollment
from app.services.course_pdf import build_course_outline
from app.services.course_readiness import compute_readiness
from app.services.course_structure import UNGROUPED_GROUP_ID, build_spine
from app.services.student_progress_service import (
    build_course_student_progress,
    build_student_chapter_detail,
)
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


# ─── Scene builders ─────────────────────────────────────────────────────
#
# ``build_spine`` reads rows, not a session, so the unit scenes below are
# transient model objects: the same classes the service is handed in
# production, without the round-trip.


def _module_row(*, title: str, order: int, course_id: str = "c") -> Module:
    return Module(id=title, course_id=course_id, title=title, order_index=order)


def _chapter_row(*, title: str, order: int, module: Module | None = None, course_id: str = "c") -> Chapter:
    return Chapter(
        id=title,
        course_id=course_id,
        module_id=module.id if module is not None else None,
        title=title,
        chapter_type="reading",
        order_index=order,
    )


def _titles(spine) -> list[str]:
    return [c.title for c in spine.chapters]


def _printed(course: Course) -> list[str]:
    """The document's sequence: a heading, then the lessons under it."""
    out: list[str] = []
    for section in build_course_outline(course):
        if section.module is not None:
            out.append(section.module.title or "")
        out.extend(c.title or "" for c in section.chapters)
    return out


def _loose_course(*, modules: list[Module], chapters: list[Chapter]) -> Course:
    """A transient course the PDF outline can be built from."""
    course = Course(
        id="c",
        title="Course",
        description="A course.",
        status=CourseStatus.DRAFT,
        access_mode="public",
        created_by=TEACHER_ID,
        source_locale="en",
    )
    course.modules = modules
    course.chapters = chapters
    return course


# ─── The three shapes a course can have ─────────────────────────────────


class TestTheThreeShapesOfACourse:
    def test_a_course_of_headings_reads_heading_by_heading(self) -> None:
        """Every lesson grouped — the shape every course built before the
        move has, and the one all three published courses still have."""
        one = _module_row(title="One", order=0)
        two = _module_row(title="Two", order=1)
        chapters = [
            _chapter_row(title="two-a", order=0, module=two),
            _chapter_row(title="one-a", order=0, module=one),
            _chapter_row(title="one-b", order=1, module=one),
            _chapter_row(title="two-b", order=1, module=two),
        ]

        spine = build_spine([two, one], chapters)

        assert _titles(spine) == ["one-a", "one-b", "two-a", "two-b"]
        assert spine.group_ids == ("One", "Two")
        assert spine.has_ungrouped is False

    def test_a_course_of_lessons_reads_by_lesson_number(self) -> None:
        """No headings at all — a short course written straight into the
        course. There is nothing to group by, so the lesson numbers are
        the whole answer."""
        chapters = [
            _chapter_row(title="third", order=2),
            _chapter_row(title="first", order=0),
            _chapter_row(title="second", order=1),
        ]

        spine = build_spine([], chapters)

        assert _titles(spine) == ["first", "second", "third"]
        assert spine.group_ids == (UNGROUPED_GROUP_ID,)
        assert all(g == UNGROUPED_GROUP_ID for g in spine.group_of.values())

    def test_a_mixed_course_keeps_the_heading_whole_and_the_loose_lesson_placed(self) -> None:
        """Some lessons grouped, some held by the course directly."""
        module = _module_row(title="Middle", order=1)
        chapters = [
            _chapter_row(title="opening", order=0),
            _chapter_row(title="mid-a", order=2, module=module),
            _chapter_row(title="mid-b", order=3, module=module),
            _chapter_row(title="closing", order=4),
        ]

        spine = build_spine([module], chapters)

        assert _titles(spine) == ["opening", "mid-a", "mid-b", "closing"]
        assert [(r.group_id, [c.title for c in r.chapters]) for r in spine.runs] == [
            (UNGROUPED_GROUP_ID, ["opening"]),
            ("Middle", ["mid-a", "mid-b"]),
            (UNGROUPED_GROUP_ID, ["closing"]),
        ]


# ─── The two cases that decided the rule ────────────────────────────────


class TestTheCasesThatDecidedTheRule:
    def test_a_loose_lesson_between_two_headings_stays_between_them(self) -> None:
        """The teacher put this lesson between two modules. Sweeping it to
        the end of the course would be a decision nobody made."""
        first = _module_row(title="First", order=0)
        second = _module_row(title="Second", order=4)
        chapters = [
            _chapter_row(title="first-a", order=1, module=first),
            _chapter_row(title="first-b", order=2, module=first),
            _chapter_row(title="interlude", order=3),
            _chapter_row(title="second-a", order=5, module=second),
            _chapter_row(title="second-b", order=6, module=second),
        ]

        spine = build_spine([first, second], chapters)

        assert _titles(spine) == ["first-a", "first-b", "interlude", "second-a", "second-b"]
        # And the board can key it to a group that sorts into that gap.
        assert spine.group_ids == ("First", UNGROUPED_GROUP_ID, "Second")
        assert spine.rank_of(UNGROUPED_GROUP_ID) == 1

    def test_renumbering_a_modules_lessons_moves_nothing_outside_it(self) -> None:
        """The defect this rule replaced: a module's lessons renumbered
        0..n-1 by a reorder inside it carried the loose lesson after the
        module in front of it. Inside a module a number orders only that
        module's lessons."""
        first = _module_row(title="First", order=0)
        chapters = [
            _chapter_row(title="first-a", order=1, module=first),
            _chapter_row(title="first-b", order=2, module=first),
            _chapter_row(title="after", order=3),
        ]
        assert _titles(build_spine([first], chapters)) == ["first-a", "first-b", "after"]

        # The teacher swaps the two lessons; an old client renumbered from 0.
        chapters[0].order_index, chapters[1].order_index = 1, 0

        assert _titles(build_spine([first], chapters)) == ["first-b", "first-a", "after"]

        # Even numbers far past the loose lesson keep the lessons in their module.
        chapters[0].order_index, chapters[1].order_index = 90, 91
        assert _titles(build_spine([first], chapters)) == ["first-a", "first-b", "after"]

    def test_moving_a_heading_moves_its_lessons_with_it(self) -> None:
        """The case the flat rule could not survive.

        Reordering a heading does not renumber the lessons under it —
        no write path does that, and production is full of courses where
        every module's lessons start at zero. A course walked by lesson
        number alone would show the teacher's move as no change at all,
        or as a shuffle: here the flat order 0,0,1,1 says nothing.
        """
        first = _module_row(title="First", order=0)
        second = _module_row(title="Second", order=1)
        chapters = [
            _chapter_row(title="first-a", order=0, module=first),
            _chapter_row(title="first-b", order=1, module=first),
            _chapter_row(title="second-a", order=0, module=second),
            _chapter_row(title="second-b", order=1, module=second),
        ]

        assert _titles(build_spine([first, second], chapters)) == [
            "first-a",
            "first-b",
            "second-a",
            "second-b",
        ]

        # The teacher drags the second heading above the first. Only the
        # two module rows change; not one lesson is renumbered.
        first.order_index = 1
        second.order_index = 0

        spine = build_spine([first, second], chapters)

        assert _titles(spine) == ["second-a", "second-b", "first-a", "first-b"]
        assert spine.group_ids == ("Second", "First")


# ─── The awkward rows ───────────────────────────────────────────────────


class TestTheAwkwardRows:
    def test_a_heading_with_no_lessons_keeps_its_place(self) -> None:
        """The teacher made it; the spine carries it. What a surface does
        with an empty heading is that surface's business — the PDF prints
        no rubric over nothing, the board still lists it."""
        first = _module_row(title="First", order=0)
        hollow = _module_row(title="Hollow", order=2)
        last = _module_row(title="Last", order=3)
        chapters = [
            _chapter_row(title="first-a", order=1, module=first),
            _chapter_row(title="last-a", order=4, module=last),
        ]

        spine = build_spine([first, hollow, last], chapters)

        assert spine.group_ids == ("First", "Hollow", "Last")
        assert _titles(spine) == ["first-a", "last-a"]
        assert [r.group_id for r in spine.runs] == ["First", "Hollow", "Last"]

    def test_a_lesson_naming_a_heading_the_course_no_longer_has_is_loose_not_lost(self) -> None:
        """``delete_module`` detaches live chapters as it bins the module,
        but a row written before that rule can still point at a binned
        one. Losing a lesson is the failure this module exists to
        prevent."""
        live = _module_row(title="Live", order=0)
        binned = _module_row(title="Binned", order=1)
        orphan = _chapter_row(title="orphan", order=1, module=binned)
        chapters = [_chapter_row(title="live-a", order=0, module=live), orphan]

        spine = build_spine([live], chapters)

        assert _titles(spine) == ["live-a", "orphan"]
        assert spine.group_of[orphan.id] == UNGROUPED_GROUP_ID

    def test_an_empty_heading_can_stand_after_a_loose_lesson(self) -> None:
        """The previous rule placed an empty module right after the module
        before it, so a teacher could not put one after a loose lesson."""
        hollow = _module_row(title="Hollow", order=1)
        chapters = [_chapter_row(title="intro", order=0), _chapter_row(title="outro", order=2)]

        spine = build_spine([hollow], chapters)

        assert [(r.group_id, [c.title for c in r.chapters]) for r in spine.runs] == [
            (UNGROUPED_GROUP_ID, ["intro"]),
            ("Hollow", []),
            (UNGROUPED_GROUP_ID, ["outro"]),
        ]

    def test_a_lesson_appended_to_an_early_heading_stays_in_it(self) -> None:
        """A new lesson takes the course's highest number plus one, so a
        lesson appended to the *first* heading carries the highest number
        in the course. It still reads at the end of its own module."""
        first = _module_row(title="First", order=0)
        second = _module_row(title="Second", order=4)
        chapters = [
            _chapter_row(title="first-a", order=1, module=first),
            _chapter_row(title="first-b", order=2, module=first),
            _chapter_row(title="interlude", order=3),
            _chapter_row(title="second-a", order=5, module=second),
            # Appended to the first heading, long after the rest existed.
            _chapter_row(title="first-late", order=6, module=first),
        ]

        spine = build_spine([first, second], chapters)

        assert _titles(spine) == ["first-a", "first-b", "first-late", "interlude", "second-a"]

    def test_ties_go_module_first_then_by_id(self) -> None:
        """Only hand-edited or legacy rows tie; every reader breaks the tie
        the same way (the client mirrors it)."""
        module = _module_row(title="M", order=1)
        chapters = [
            _chapter_row(title="b-loose", order=1),
            _chapter_row(title="a-loose", order=1),
            _chapter_row(title="inside", order=0, module=module),
        ]

        assert _titles(build_spine([module], chapters)) == ["inside", "a-loose", "b-loose"]


# ─── One rule, every surface ────────────────────────────────────────────


class TestEverySurfaceReadsTheSameOrder:
    """The point of the change: not that the rule is this one, but that
    there is one of it. Each of these used to answer differently."""

    def test_the_document_prints_the_spine(self) -> None:
        first = _module_row(title="First", order=0)
        second = _module_row(title="Second", order=3)
        chapters = [
            _chapter_row(title="first-a", order=1, module=first),
            _chapter_row(title="interlude", order=2),
            _chapter_row(title="second-a", order=4, module=second),
        ]
        course = _loose_course(modules=[first, second], chapters=chapters)

        spine = build_spine([first, second], chapters)

        assert _printed(course) == ["First", "first-a", "interlude", "Second", "second-a"]
        assert [c.title for s in build_course_outline(course) for c in s.chapters] == _titles(spine)

    def test_the_checklist_and_the_board_walk_the_course_in_that_same_order(
        self, db: Session, teacher: User, student: User
    ) -> None:
        course = Course(
            id=str(uuid.uuid4()),
            title="Course",
            description="A description, so the catalog checks are not the noise.",
            image_url="https://example.org/cover.png",
            status=CourseStatus.DRAFT,
            access_mode="public",
            created_by=TEACHER_ID,
            source_locale="en",
        )
        db.add(course)
        db.flush()

        def module(title: str, order: int) -> Module:
            row = Module(id=str(uuid.uuid4()), course_id=course.id, title=title, order_index=order)
            db.add(row)
            db.flush()
            return row

        def chapter(title: str, order: int, group: Module | None) -> Chapter:
            row = Chapter(
                id=str(uuid.uuid4()),
                course_id=course.id,
                module_id=group.id if group is not None else None,
                title=title,
                chapter_type="reading",
                order_index=order,
            )
            db.add(row)
            db.flush()
            return row

        first = module("First", 0)
        second = module("Second", 3)
        rows = [
            chapter("first-a", 1, first),
            chapter("interlude", 2, None),
            chapter("second-a", 4, second),
        ]
        db.add(Enrollment(id=str(uuid.uuid4()), user_id=STUDENT_ID, course_id=course.id, progress=0))
        db.commit()
        db.refresh(course)

        expected = [r.id for r in rows]

        # The checklist: its per-chapter checks come out in spine order.
        report = compute_readiness(db, course)
        checked = [c.subject.id for c in report.checks if c.subject is not None and c.subject.type == "chapter"]
        assert [cid for i, cid in enumerate(checked) if cid not in checked[:i]] == expected

        # The board, and the group the loose lesson keys to.
        detail = build_student_chapter_detail(db, course, course.id, str(STUDENT_ID))
        assert [ch["id"] for ch in detail["chapters"]] == expected
        assert detail["chapters"][1]["module_id"] == UNGROUPED_GROUP_ID

        # The group list the client sorts by ``order_index`` has to land
        # the loose stretch between the two headings.
        board = build_course_student_progress(db, course, course.id)
        groups = sorted(board["modules"], key=lambda g: g["order_index"])
        assert [g["id"] for g in groups] == [first.id, UNGROUPED_GROUP_ID, second.id]

        # The document.
        assert [c.id for s in build_course_outline(course) for c in s.chapters] == expected
