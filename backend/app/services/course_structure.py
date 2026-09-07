"""One answer to "in what order does this course read?".

A chapter belongs to its course; a module is an optional heading that
groups some of them. That leaves a course with two kinds of lesson —
grouped and loose — and every surface that walks a course has to give
the same answer about how the two interleave. The readiness checklist,
the teacher's progress board and the PDF export all walk a course, and
until this module they walked it three ways.

The rule, decided once and applied everywhere:

* **the headings run in the order the teacher gave them** —
  ``module.order_index``, ties broken by id;
* **a heading's lessons run consecutively** under it, in their own
  ``order_index``: a heading whose lessons are scattered is not a
  heading;
* **a lesson in no module sits where its own ``order_index`` puts it** —
  before the first heading whose lessons start above it. It has no
  heading to sit under, so the only thing left to honour is the number
  the author gave it.

The third clause is the one that replaces an assumption with an order.
The board used to park every loose lesson in a tail after the last
module: not where the author put it, just where nothing else was. The
PDF used to sort the whole course flat by ``chapter.order_index`` and
let a module take the position of its first lesson — which reads well
but assumes that number means something across the whole course, and
:func:`build_spine` is where that assumption is not made.

Why the two numbers are not one number. ``module.order_index`` is the
authored order of headings and ``chapter.order_index`` the authored
order of lessons, and they answer different questions: moving a heading
does not renumber the lessons under it. A flat sort by lesson number
alone would therefore quietly ignore a heading the teacher had just
moved — so headings are ordered by the number that tracks them, and
lesson numbers decide only what a lesson number can decide: the order
inside a heading, and where a loose lesson falls between headings.

That second use does need lesson numbers to mean something across the
course, and since 2026-09-07 they do: ``_next_chapter_order`` gives a
new chapter the course maximum plus one whichever module it lands in.
Rows written before that date were numbered per module — every module
restarting at zero — and the migration
``20260908..._one_order_for_the_course`` renumbers them, without moving
anything anybody can see.

Where the numbering is scrambled anyway (a heading moved, its lessons
left behind), the heading order still wins and the fallback below keeps
the sequence total rather than surprising: a heading never starts below
the one before it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

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
        number to sort it by — a module's own ``order_index`` cannot say
        where a loose stretch falls between two modules, because both
        neighbours have already taken their integer.
        """
        return self.group_ids.index(group_id)


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
    loose.sort(key=lambda c: (c.order_index, c.id))

    headings = sorted(modules, key=lambda m: (m.order_index, m.id))

    # Where each heading starts, in lesson numbers — the cut a loose
    # lesson is compared against. Running maximum, so the cuts ascend
    # even when the lesson numbers do not: a heading that was moved above
    # one whose lessons are numbered lower keeps its authored place, and
    # no loose lesson is dragged backwards through it. An empty heading
    # inherits the cut of the heading before it, which is what "it has no
    # lessons of its own to start at" comes to.
    starts: list[int] = []
    running = -1
    for module in headings:
        members = grouped.get(module.id) or []
        if members:
            running = max(running, members[0].order_index)
        starts.append(running)

    runs: list[SpineRun] = []
    taken = 0

    def _emit_loose(limit: int | None) -> None:
        """Emit the loose lessons numbered below ``limit`` as one run.

        ``None`` means "everything left" — the tail. Consecutive loose
        lessons share a run: they carry no heading, so splitting them
        would only scatter a flat course.
        """
        nonlocal taken
        start = taken
        while taken < len(loose) and (limit is None or loose[taken].order_index < limit):
            taken += 1
        if taken > start:
            runs.append(SpineRun(module=None, chapters=tuple(loose[start:taken])))

    for module, start in zip(headings, starts, strict=True):
        _emit_loose(start)
        runs.append(SpineRun(module=module, chapters=tuple(grouped.get(module.id) or ())))
    _emit_loose(None)

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
