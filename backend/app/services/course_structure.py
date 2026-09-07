"""One answer to "in what order does this course read?".

A chapter belongs to its course; a module is an optional heading that
groups some of them. That leaves a course with two kinds of lesson —
grouped and loose — and every surface that walks a course needs the same
answer about how the two interleave. The readiness checklist and the
teacher's progress board both used to walk modules and quietly lose the
loose chapters; they now walk the course through this module instead.

The rule, decided once and applied everywhere:

* the order is **course-global** — one flat sequence of chapters;
* **a group's chapters run consecutively** — a module is a heading, and
  a heading whose lessons are scattered is not a heading;
* groups follow the modules' own ``order_index``, and the chapters that
  belong to no module come **last**. A module is an authored position in
  the spine; a loose chapter has no position among modules to claim, and
  the tail is where new chapters are appended anyway.

The first two thirds of that are not a new rule: it is the one
``_next_chapter_order`` already states as the thing it must not disturb
— "chapters render as modules by ``module.order_index``, then chapters
by ``order_index`` inside each module". This module is where that
sentence is executed rather than described, plus the answer to the case
it does not cover: where the chapters with no module go.

Since 2026-09-07 ``order_index`` is course-global — a new chapter takes
the course's maximum plus one, whichever module it lands in. Grouping
still comes first when reading, because the two numbers answer
different questions: ``module.order_index`` is the teacher's authored
order of headings, and reordering a module does not renumber its
chapters. Sorting the flat course by chapter ``order_index`` alone
would therefore quietly ignore a module the teacher had just moved.
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
class CourseSpine:
    """How one course reads: its groups in order, its chapters in order,
    and which group each chapter renders under."""

    #: Module ids in reading order, plus :data:`UNGROUPED_GROUP_ID` at
    #: the end when the course has at least one chapter outside every
    #: module. Modules with no chapters are included — the teacher made
    #: them and should keep seeing them.
    group_ids: tuple[str, ...]
    #: Every chapter handed in, course-global order, groups consecutive.
    chapters: tuple[Chapter, ...]
    #: ``chapter.id -> group id``. Every chapter in :attr:`chapters` has
    #: an entry, and every value is one of :attr:`group_ids`.
    group_of: dict[str, str]

    @property
    def has_ungrouped(self) -> bool:
        return UNGROUPED_GROUP_ID in self.group_ids


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
    for chapter in chapters:
        module_id = chapter.module_id
        group_of[chapter.id] = module_id if module_id is not None and module_id in module_ids else UNGROUPED_GROUP_ID

    group_ids = [m.id for m in sorted(modules, key=lambda m: (m.order_index, m.id))]
    if UNGROUPED_GROUP_ID in group_of.values():
        group_ids.append(UNGROUPED_GROUP_ID)
    rank = {group_id: index for index, group_id in enumerate(group_ids)}

    ordered = sorted(chapters, key=lambda c: (rank[group_of[c.id]], c.order_index, c.id))
    return CourseSpine(group_ids=tuple(group_ids), chapters=tuple(ordered), group_of=group_of)
