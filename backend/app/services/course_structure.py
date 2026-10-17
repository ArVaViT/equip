"""One answer to "in what order does this course read?".

A chapter belongs to its course; a module is an optional heading that
groups some of them. That leaves a course with two kinds of lesson —
grouped and loose — and every surface that walks a course has to give
the same answer about how the two interleave: the student's course page,
"next lesson", the sequential lock, the teacher's editor and board, the
readiness checklist and the PDF.

The rule (2026-10-16, Vadym's decision: one order for everybody, the one
the teacher set):

* **the course is one sequence of places.** A module takes a place, and
  so does every lesson that sits in no module. Both are numbered by
  their own ``order_index`` in one shared space — a module's number and
  a loose lesson's number are compared with each other directly;
* **a module's lessons run consecutively under it**, in their own
  ``order_index``. Inside a module that number only orders the module's
  lessons; it is never compared with anything outside the module;
* ties (only possible in hand-edited or legacy rows) go module first,
  then by id, so every reader breaks them the same way.

So a lesson the teacher put between two modules stays between them, for
the teacher and the student alike, and reordering the lessons inside a
module cannot move anything outside it — the defect the previous rule
had, where a loose lesson was placed by comparing its number with the
numbers of the lessons a module *started* with, and renumbering one
module's lessons could carry a loose lesson past it.

The write side keeps the numbers clean: :func:`number_outline` hands out
one counter over the whole course in reading order — a module, then its
lessons, then the next place — so the numbers are also monotonic across
the course, and the migration
``20261016120000_one_sequence_for_modules_and_loose_lessons`` brought
the existing rows into that shape without moving anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from app.models.course import Chapter, Module

# The group id standing for "this chapter is in no module". Reports send
# it where a ``module_id`` would go, so a client can key loose chapters
# to a group it can actually render instead of dropping them.
#
# Module ids are UUID strings, so this can never collide with a real one.
UNGROUPED_GROUP_ID = "__ungrouped__"


@dataclass(frozen=True)
class SpineRun:
    """One consecutive stretch of the course: a heading with its lessons,
    or a stretch of lessons no heading covers.

    ``module`` is ``None`` for a loose stretch — a lesson that belongs
    straight to the course sits under the course, not under an invented
    rubric. A module the teacher made but has not filled yet appears as a
    run with no chapters: it is still part of the spine, and a surface
    that prints headings over lessons simply skips it.
    """

    module: Module | None
    chapters: tuple[Chapter, ...]

    @property
    def group_id(self) -> str:
        return UNGROUPED_GROUP_ID if self.module is None else self.module.id


@dataclass(frozen=True)
class CourseSpine:
    """How one course reads: its runs in order, its chapters in order,
    and which group each chapter renders under."""

    #: Group ids in reading order — module ids, plus
    #: :data:`UNGROUPED_GROUP_ID` at the position of the first loose
    #: stretch when the course has one. Modules with no chapters are
    #: included: the teacher made them and should keep seeing them.
    group_ids: tuple[str, ...]
    #: Every chapter handed in, course reading order, groups consecutive.
    chapters: tuple[Chapter, ...]
    #: ``chapter.id -> group id``. Every chapter in :attr:`chapters` has
    #: an entry, and every value is one of :attr:`group_ids`.
    group_of: dict[str, str]
    #: The same sequence cut into headings and the lessons under them.
    #: A course can hold more than one loose stretch, so a group id can
    #: appear in more than one run — only :data:`UNGROUPED_GROUP_ID`
    #: ever does.
    runs: tuple[SpineRun, ...]

    @property
    def has_ungrouped(self) -> bool:
        return UNGROUPED_GROUP_ID in self.group_ids

    def rank_of(self, group_id: str) -> int:
        """Where this group sits in the reading order, counting from 0.

        The board hands its clients a group list to sort, and this is the
        number to sort it by — the client sorts groups, and a course can
        hold several loose stretches that report as one group.
        """
        return self.group_ids.index(group_id)

    def predecessor_of(self, chapter_id: str) -> Chapter | None:
        """The lesson a reader meets just before this one, across module
        boundaries; ``None`` for the first lesson or one not in the spine."""
        for index, chapter in enumerate(self.chapters):
            if chapter.id == chapter_id:
                return self.chapters[index - 1] if index > 0 else None
        return None


def build_spine(modules: Sequence[Module], chapters: Sequence[Chapter]) -> CourseSpine:
    """Arrange ``chapters`` under ``modules`` by the rule above.

    ``modules`` and ``chapters`` are the *live* ones — callers filter
    soft-deleted rows before getting here. A chapter naming a module that
    isn't in ``modules`` anyway (a stale ``module_id``) is treated as
    loose rather than dropped: losing a lesson is the failure this whole
    module exists to prevent.
    """
    module_ids = {m.id for m in modules}
    group_of: dict[str, str] = {}
    grouped: dict[str, list[Chapter]] = {}
    loose: list[Chapter] = []
    for chapter in chapters:
        module_id = chapter.module_id
        if module_id is not None and module_id in module_ids:
            group_of[chapter.id] = module_id
            grouped.setdefault(module_id, []).append(chapter)
        else:
            group_of[chapter.id] = UNGROUPED_GROUP_ID
            loose.append(chapter)

    for members in grouped.values():
        members.sort(key=lambda c: (c.order_index, c.id))

    # The course's places: modules and loose lessons in one sort. The
    # middle key puts a module ahead of a loose lesson holding the same
    # number — arbitrary, but the same choice the client makes.
    places: list[tuple[int, int, str, Module | None, Chapter | None]] = [
        (m.order_index, 0, m.id, m, None) for m in modules
    ]
    places.extend((c.order_index, 1, c.id, None, c) for c in loose)
    places.sort(key=lambda p: (p[0], p[1], p[2]))

    runs: list[SpineRun] = []
    pending_loose: list[Chapter] = []

    def _flush_loose() -> None:
        # Consecutive loose lessons share a run: they carry no heading, so
        # splitting them would only scatter a flat course.
        if pending_loose:
            runs.append(SpineRun(module=None, chapters=tuple(pending_loose)))
            pending_loose.clear()

    for _order, _kind, _id, module, lesson in places:
        if lesson is not None:
            pending_loose.append(lesson)
        elif module is not None:
            _flush_loose()
            runs.append(SpineRun(module=module, chapters=tuple(grouped.get(module.id) or ())))
    _flush_loose()

    ordered: list[Chapter] = []
    group_ids: list[str] = []
    for run in runs:
        ordered.extend(run.chapters)
        if run.group_id not in group_ids:
            group_ids.append(run.group_id)

    return CourseSpine(
        group_ids=tuple(group_ids),
        chapters=tuple(ordered),
        group_of=group_of,
        runs=tuple(runs),
    )


@dataclass(frozen=True)
class OutlineNumbers:
    """What :func:`number_outline` hands out: a number per module, and a
    number and a module (or ``None``) per lesson."""

    modules: dict[str, int]
    chapters: dict[str, tuple[int, str | None]]


def number_outline(places: Iterable[tuple[str | None, Sequence[str]]]) -> OutlineNumbers:
    """Number a course written out as places, in reading order.

    Each place is ``(module_id, chapter_ids)`` — a module and the lessons
    under it, or ``(None, chapter_ids)`` for lessons that sit in no
    module. One counter runs over the whole course: a module takes the
    next number and its lessons the ones after it, a loose lesson takes
    the next number. The result reads back through :func:`build_spine`
    as exactly the sequence handed in, and the lesson numbers alone are
    monotonic over the course too.
    """
    counter = 0
    module_numbers: dict[str, int] = {}
    chapter_numbers: dict[str, tuple[int, str | None]] = {}
    for module_id, chapter_ids in places:
        if module_id is not None:
            module_numbers[module_id] = counter
            counter += 1
        for chapter_id in chapter_ids:
            chapter_numbers[chapter_id] = (counter, module_id)
            counter += 1
    return OutlineNumbers(modules=module_numbers, chapters=chapter_numbers)


def places_of(spine: CourseSpine) -> list[tuple[str | None, list[str]]]:
    """The spine written out as places — the input :func:`number_outline`
    takes. A loose stretch becomes one place per lesson."""
    places: list[tuple[str | None, list[str]]] = []
    for run in spine.runs:
        if run.module is None:
            places.extend((None, [c.id]) for c in run.chapters)
        else:
            places.append((run.module.id, [c.id for c in run.chapters]))
    return places
