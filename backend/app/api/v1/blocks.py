from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_chapter_access, verify_chapter_owner
from app.core.database import get_db
from app.core.sanitize import sanitize_string
from app.models.chapter_block import ChapterBlock
from app.models.user import User
from app.schemas.chapter_block import BlockCreate, BlockReorderItem, BlockResponse, BlockUpdate
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import (
    get_course_source_locale_for_chapter,
    localize_chapter_block_rows,
    should_apply_course_translation_overlay_for_chapter,
)

router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.get("/chapter/{chapter_id}", response_model=list[BlockResponse])
def list_blocks(
    chapter_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_chapter_access(db, chapter_id, current_user)
    response.headers["Vary"] = "Accept-Language"
    rows = db.query(ChapterBlock).filter(ChapterBlock.chapter_id == chapter_id).order_by(ChapterBlock.order_index).all()
    display_locale: LocaleCode = normalize_locale(accept_language)
    src = get_course_source_locale_for_chapter(db, chapter_id)
    if should_apply_course_translation_overlay_for_chapter(db, chapter_id=chapter_id, current_user=current_user):
        return localize_chapter_block_rows(db, rows, display_locale=display_locale, source_locale=src)
    return rows


@router.post(
    "/chapter/{chapter_id}",
    response_model=BlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chapter block (text / quiz / assignment / file)",
    responses={
        201: {"description": "Block persisted; translation reconcile fires async"},
        403: {"description": "Caller does not own the chapter's course"},
        404: {"description": "Chapter not found"},
        409: {"description": "Referenced ``quiz_id`` / ``assignment_id`` no longer exists"},
    },
)
def create_block(
    chapter_id: str,
    data: BlockCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Append a block to the chapter. ``order_index`` is provided by the
    client so multi-block writes preserve the intended ordering even
    when the frontend optimistically reorders before save.

    Rich text (``content``) is sanitized server-side with ``bleach``
    even though the frontend already DOMPurifies — defence-in-depth
    for direct API callers."""
    verify_chapter_owner(db, chapter_id, teacher)
    # Defence-in-depth: the frontend runs DOMPurify before sending, but a
    # direct API caller can bypass that. We re-sanitize here so stored block
    # HTML is safe to render for every downstream consumer (admin preview,
    # exports, emailed digests) — not only the main React app.
    content = sanitize_string(data.content) if data.content else data.content
    block = ChapterBlock(
        chapter_id=chapter_id,
        block_type=data.block_type,
        order_index=data.order_index,
        content=content,
        quiz_id=data.quiz_id,
        assignment_id=data.assignment_id,
        file_bucket=data.file_bucket,
        file_path=data.file_path,
        file_name=data.file_name,
    )
    db.add(block)
    try:
        db.commit()
    except IntegrityError as exc:
        # quiz_id / assignment_id are FKs — a stale client can pass an id
        # that was just deleted, tripping the FK constraint. Surface a 409
        # instead of letting SQLAlchemy raise a 500.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Referenced quiz or assignment no longer exists",
        ) from exc
    db.refresh(block)
    reconcile_entity_if_course_published(db, "chapter_block", block)
    return block


@router.put(
    "/{block_id}",
    response_model=BlockResponse,
    summary="Update a block in place",
    responses={
        200: {"description": "Block updated and translation overlay reconciled"},
        403: {"description": "Caller does not own the chapter's course"},
        404: {"description": "Block not found"},
        409: {"description": "Referenced ``quiz_id`` / ``assignment_id`` no longer exists"},
    },
)
def update_block(
    block_id: UUID,
    data: BlockUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Patch any subset of block fields. ``content`` is sanitized
    server-side. Changing ``block_type`` is allowed (e.g. text → quiz)
    but the client should clear / set the type-specific fields
    (``quiz_id``, ``assignment_id``, ``file_*``) consistently;
    constraints aren't enforced at the schema layer because writes from
    the editor never mix types in the same patch."""
    block = db.query(ChapterBlock).filter(ChapterBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    verify_chapter_owner(db, block.chapter_id, teacher)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "content" and value:
            value = sanitize_string(value)
        setattr(block, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Referenced quiz or assignment no longer exists",
        ) from exc
    db.refresh(block)
    reconcile_entity_if_course_published(db, "chapter_block", block)
    return block


@router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_block(
    block_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    block = db.query(ChapterBlock).filter(ChapterBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    verify_chapter_owner(db, block.chapter_id, teacher)
    db.delete(block)
    db.commit()
    # No reconcile after delete — the entity is gone; translation rows
    # cascade out via FK ON DELETE on content_translations.


@router.put("/chapter/{chapter_id}/reorder", response_model=list[BlockResponse])
def reorder_blocks(
    chapter_id: str,
    items: list[BlockReorderItem],
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    verify_chapter_owner(db, chapter_id, teacher)
    block_ids = [item.id for item in items]
    blocks_by_id = {
        b.id: b
        for b in db.query(ChapterBlock)
        .filter(
            ChapterBlock.id.in_(block_ids),
            ChapterBlock.chapter_id == chapter_id,
        )
        .all()
    }
    for item in items:
        block = blocks_by_id.get(item.id)
        if block:
            block.order_index = item.order_index
    db.commit()
    return db.query(ChapterBlock).filter(ChapterBlock.chapter_id == chapter_id).order_by(ChapterBlock.order_index).all()
