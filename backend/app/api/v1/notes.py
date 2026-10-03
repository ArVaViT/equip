"""A student's own notes on lessons: one beside each lesson, and all of them on one page.

Only ever the caller's: every query is filtered by their id, and writing a
note on a lesson needs the same access as reading the lesson. An empty note
is no note — saving one deletes the row.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session  # noqa: TC002

from app.api.dependencies import get_current_user, verify_chapter_access
from app.core.database import get_db
from app.models.chapter_note import ChapterNote
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from app.schemas.locale import normalize_locale
from app.services.content_versions import fetch_cv_entity_texts_with_fallback

router = APIRouter(prefix="/notes", tags=["notes"])

NOTE_MAX_LENGTH = 10_000


class NoteWrite(BaseModel):
    body: str = Field(..., max_length=NOTE_MAX_LENGTH)


class Note(BaseModel):
    chapter_id: str
    body: str | None
    updated_at: datetime | None = None


class NoteInList(BaseModel):
    chapter_id: str
    chapter_title: str | None
    module_id: str | None
    module_title: str | None
    course_id: str
    course_title: str | None
    body: str
    updated_at: datetime
    #: Whether the lesson can still be opened by the caller. A course since
    #: unpublished or left keeps the student's words on the page, without a
    #: link that would lead to a 404.
    available: bool


@router.get("/chapters/{chapter_id}", response_model=Note)
def read_note(
    chapter_id: str,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Note:
    verify_chapter_access(db, chapter_id, current_user)
    response.headers["Cache-Control"] = "no-store"
    note = db.get(ChapterNote, (current_user.id, chapter_id))
    return Note(chapter_id=chapter_id, body=note.body if note else None, updated_at=note.updated_at if note else None)


@router.put("/chapters/{chapter_id}", response_model=Note)
def write_note(
    chapter_id: str,
    data: NoteWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Note:
    verify_chapter_access(db, chapter_id, current_user)
    body = data.body.strip()
    note = db.get(ChapterNote, (current_user.id, chapter_id))
    if not body:
        if note is not None:
            db.delete(note)
            db.commit()
        return Note(chapter_id=chapter_id, body=None)
    if note is None:
        note = ChapterNote(user_id=current_user.id, chapter_id=chapter_id, body=body)
        try:
            # Two saves of a new note can cross (a blur and leaving the
            # lesson); the second insert must update, not answer 500.
            with db.begin_nested():
                db.add(note)
                db.flush()
        except IntegrityError:
            note = db.get(ChapterNote, (current_user.id, chapter_id), populate_existing=True)
            assert note is not None
            note.body = body
    else:
        note.body = body
    db.commit()
    db.refresh(note)
    return Note(chapter_id=chapter_id, body=note.body, updated_at=note.updated_at)


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    chapter_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # No access check: a student may always remove their own words, even
    # from a course they have since left.
    db.query(ChapterNote).filter(ChapterNote.user_id == current_user.id, ChapterNote.chapter_id == chapter_id).delete()
    db.commit()


@router.get("/me/chapters", response_model=list[str])
def my_noted_chapters(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[str]:
    """Only which lessons have a note — for marking them in a list, without
    sending every note's text and looking up every title to do it."""
    response.headers["Cache-Control"] = "no-store"
    return [
        chapter_id
        for (chapter_id,) in db.query(ChapterNote.chapter_id)
        .join(Chapter, Chapter.id == ChapterNote.chapter_id)
        .filter(ChapterNote.user_id == current_user.id, Chapter.deleted_at.is_(None))
        .all()
    ]


@router.get("/me", response_model=list[NoteInList])
def my_notes(
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NoteInList]:
    """Every note of the caller's, with where it belongs, in course order.

    Titles in the reader's language only (``fallback="none"``): a lesson not
    translated yet comes back without a title and the page says so, rather
    than in another language.
    """
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Accept-Language"
    locale = normalize_locale(accept_language, fallback="en")
    rows = (
        db.query(ChapterNote, Chapter, Module, Course)
        .join(Chapter, Chapter.id == ChapterNote.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .outerjoin(Module, Module.id == Chapter.module_id)
        .filter(
            ChapterNote.user_id == current_user.id,
            # In the bin is gone for the reader too; the note returns with
            # the lesson if it is restored.
            Chapter.deleted_at.is_(None),
            Course.deleted_at.is_(None),
        )
        .all()
    )
    enrolled = {
        course_id
        for (course_id,) in db.query(Enrollment.course_id).filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id.in_({course.id for _, _, _, course in rows}),
        )
    }
    titles: dict[tuple[str, str, str], str | None] = {}
    by_source: dict[str, list[tuple[Chapter, Module | None, Course]]] = {}
    for _note, chapter, module, course in rows:
        by_source.setdefault(course.source_locale or "en", []).append((chapter, module, course))
    for source, items in by_source.items():
        for entity_type, ids in (
            ("chapter", [c.id for c, _, _ in items]),
            ("module", [m.id for _, m, _ in items if m is not None]),
            ("course", [k.id for _, _, k in items]),
        ):
            if not ids:
                continue
            texts = fetch_cv_entity_texts_with_fallback(
                db,
                entity_type=entity_type,
                entity_ids=list(dict.fromkeys(ids)),
                fields=["title"],
                display_locale=locale,
                source_locale=source,
                fallback="none",
            )
            for (entity_id, _field), text in texts.items():
                titles[(entity_type, entity_id, "title")] = text

    def opens(course: Course) -> bool:
        # The publication and enrolment half of reading the lesson
        # (``verify_chapter_access``); a lesson's own lock is not counted,
        # so a locked lesson's link can still answer 403.
        return (
            current_user.role == UserRole.ADMIN.value
            or str(course.created_by) == str(current_user.id)
            or (course.status == CourseStatus.PUBLISHED and course.id in enrolled)
        )

    out: list[NoteInList] = []
    for note, chapter, module, course in rows:
        available = opens(course)
        # A course since unpublished or left keeps the student's words, but
        # not its current titles: a draft renamed after they left is not
        # theirs to read.
        out.append(
            NoteInList(
                chapter_id=chapter.id,
                chapter_title=titles.get(("chapter", chapter.id, "title")) if available else None,
                module_id=module.id if module else None,
                module_title=titles.get(("module", module.id, "title")) if module and available else None,
                course_id=course.id,
                course_title=titles.get(("course", course.id, "title")) if available else None,
                body=note.body,
                updated_at=note.updated_at,
                available=available,
            )
        )
    order = {(c.id): (m.order_index if m else 10_000, c.order_index) for _, c, m, _ in rows}
    out.sort(key=lambda n: (n.course_title or "", n.course_id, order[n.chapter_id]))
    return out
