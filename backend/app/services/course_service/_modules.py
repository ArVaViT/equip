"""Module write operations (create / update / soft-delete)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, Module
from app.schemas.locale import normalize_locale
from app.services.content_versions import dual_write_entity_content
from app.services.course_service._outline import OutlinePlaceError, live_spine, next_outline_order, write_outline
from app.services.course_structure import places_of
from app.services.translation.resolve_for_display import populate_module_texts

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.course import ModuleCreate, ModuleUpdate


def _next_module_order(db: Session, course_id: str) -> int:
    """Return the tail ``order_index`` for a new module on this course.

    Past the lessons that sit in no module as well as past the other
    modules: the two share one sequence (``course_structure``), and a new
    module numbered only past the modules would land in front of a loose
    lesson the teacher had put at the end.
    """
    return next_outline_order(db, course_id)


def _course_source_locale(db: Session, course_id: str) -> str | None:
    """Cheap single-column lookup of the parent course's source locale.

    Used as the per-field detection fallback when a module / chapter
    title can't be classified on its own (short titles like "1" or
    "Часть 1" often can't).
    """
    return db.query(Course.source_locale).filter(Course.id == course_id).scalar()


def create_module(db: Session, course_id: str, data: ModuleCreate) -> Module:
    # If the client left ``order_index`` at its default (0) and the course
    # already has modules, append at the tail instead of silently colliding.
    # Clients that need a specific slot (e.g. drag-and-drop reorder) still
    # pass their explicit index and control the full layout themselves.
    order_index = data.order_index if data.order_index else _next_module_order(db, course_id)
    # Title + description columns dropped. Structural row only;
    # texts routed via the ``texts={...}`` dict variant of dual_write.
    module = Module(
        id=str(uuid.uuid4()),
        course_id=course_id,
        order_index=order_index,
        due_date=data.due_date,
    )
    db.add(module)
    db.flush()
    dual_write_entity_content(
        db,
        entity_type="module",
        entity_id=str(module.id),
        fallback_locale=_course_source_locale(db, course_id),
        texts={"title": data.title, "description": data.description},
    )
    db.commit()
    db.refresh(module)
    # Hydrate runtime attrs for response serialization.
    module.title = data.title
    module.description = data.description
    return module


def update_module(db: Session, module: Module, data: ModuleUpdate) -> Module:
    patch = data.model_dump(exclude_unset=True)
    # A module's place is a place in the course's shared sequence: only the
    # outline writes it (``OutlinePlaceError``). The number it already has
    # — a client echoing the row back — or ``null`` changes nothing.
    if "order_index" in patch:
        wanted = patch.pop("order_index")
        if wanted is not None and wanted != module.order_index:
            raise OutlinePlaceError("A module's place in the course is set through PUT /courses/{id}/outline")
    # Text fields live in cv. Pop them off the patch before
    # setattr-loop on the (now-text-less) ORM row.
    text_patch: dict[str, str | None] = {}
    if "title" in patch:
        text_patch["title"] = patch.pop("title")
    if "description" in patch:
        text_patch["description"] = patch.pop("description")
    for field, value in patch.items():
        setattr(module, field, value)
    db.flush()
    if text_patch:
        dual_write_entity_content(
            db,
            entity_type="module",
            entity_id=str(module.id),
            fallback_locale=_course_source_locale(db, module.course_id),
            only_fields=set(text_patch.keys()),
            texts=text_patch,
        )
    db.commit()
    db.refresh(module)
    # Hydrate runtime attrs from cv so the caller's serialization picks
    # up the new text immediately.
    src = _course_source_locale(db, module.course_id) or "en"
    populate_module_texts(db, [module], source_locale=normalize_locale(src), for_author=True)
    return module


def delete_module(db: Session, module: Module) -> None:
    """Bin the grouping; the lessons stay on the course.

    Until the module became optional this binned every chapter under it,
    because a chapter could not exist without a module — there was
    nowhere for it to go. There is now: a chapter belongs to its course
    and only names a module. So deleting a module deletes a heading, and
    its chapters surface at the course, ungrouped, untouched
    (``deleted_at`` is deliberately not written).

    This is the whole point of the change. The teacher who prompted it
    lost lessons to exactly this cascade: they were reshaping the tree,
    deleted a module they had invented to satisfy the old model, and the
    work went with it.

    Bulk UPDATE so the detach is one round trip regardless of chapter
    count, and works whether ``module.chapters`` was eager-loaded with a
    ``deleted_at`` filter or not. Chapters already in the bin keep the
    module they were binned under — that is history, and nothing reads a
    binned chapter's module.

    No progress resync: the set of live gradable chapters on the course
    is exactly what it was a moment ago, so no denominator moved. The
    old implementation resynced because this call used to delete
    quizzes.
    """
    # The freed lessons take the module's place in the course, in the
    # module's order. Their numbers alone cannot say that: inside a module
    # a number only orders the module's own lessons, and one appended
    # late carries the course's highest — freed as is, it would jump to
    # the end of the course.
    places: list[tuple[str | None, list[str]]] = []
    for place_module, ids in places_of(live_spine(db, module.course_id)):
        if place_module == module.id:
            places.extend((None, [chapter_id]) for chapter_id in ids)
        else:
            places.append((place_module, ids))
    module.deleted_at = datetime.now(UTC)
    db.query(Chapter).filter(
        Chapter.module_id == module.id,
        Chapter.deleted_at.is_(None),
    ).update({Chapter.module_id: None}, synchronize_session=False)
    db.flush()
    db.expire_all()
    write_outline(db, module.course_id, places)
    db.commit()
