from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_chapter_access, verify_chapter_owner
from app.core.database import get_db
from app.core.sanitize import sanitize_string
from app.models.chapter_block import ChapterBlock
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.user import User
from app.schemas.chapter_block import BlockCreate, BlockReorderItem, BlockResponse, BlockUpdate
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.content_versions import dual_write_entity_content
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import (
    localize_chapter_block_rows,
    resolve_chapter_locale_context,
)

router = APIRouter(prefix="/blocks", tags=["blocks"])


_TRANSLATABLE_BLOCK_FIELDS = ("content",)


def _block_to_response(db: Session, block: ChapterBlock) -> BlockResponse:
    """Phase 5e2: chapter_blocks.content column dropped — build the
    response with content pulled from cv (source-locale row preferred).
    Used by the single-block routes (create / update) which return one
    block; the list/get routes use ``localize_chapter_block_rows``
    which is locale-aware.
    """
    row = (
        db.query(ContentVersion.text)
        .filter(
            ContentVersion.entity_type == "chapter_block",
            ContentVersion.entity_id == str(block.id),
            ContentVersion.field == "content",
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == "ok",
        )
        .order_by(ContentVersion.created_at)
        .first()
    )
    content = row.text if row is not None else None
    # ``model_validate(dict)`` so Pydantic handles the ``created_at``
    # nullability coercion (the ORM column is ``Optional[datetime]``
    # at type-time but server_default=now() means it's set by the time
    # we read it back after refresh).
    return BlockResponse.model_validate(
        {
            "id": block.id,
            "chapter_id": block.chapter_id,
            "block_type": block.block_type,
            "order_index": block.order_index,
            "content": content,
            "quiz_id": block.quiz_id,
            "assignment_id": block.assignment_id,
            "file_bucket": block.file_bucket,
            "file_path": block.file_path,
            "file_name": block.file_name,
            "created_at": block.created_at,
            "updated_at": block.updated_at,
        }
    )


def _course_source_locale_for_chapter(db: Session, chapter_id: str) -> str | None:
    """Walk ``ChapterBlock -> Chapter -> Module -> Course`` to find the
    parent course's source locale for use as the dual-write fallback
    when block ``content`` is too short or non-letter for the
    detector to classify on its own.
    """
    return (
        db.query(Course.source_locale)
        .join(Module, Module.course_id == Course.id)
        .join(Chapter, Chapter.module_id == Module.id)
        .filter(Chapter.id == chapter_id)
        .scalar()
    )


@router.get("/chapter/{chapter_id}", response_model=list[BlockResponse])
def list_blocks(
    chapter_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    source: bool = Query(
        False,
        description=(
            "Bypass the translation overlay and return source-language ``content`` "
            "(rich-text HTML). Owner / admin only — used by the chapter block "
            "editor so a teacher viewing their RU course in EN UI doesn't "
            "accidentally save the EN translation back into the source content."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_chapter_access(db, chapter_id, current_user)
    response.headers["Vary"] = "Accept-Language"
    rows = db.query(ChapterBlock).filter(ChapterBlock.chapter_id == chapter_id).order_by(ChapterBlock.order_index).all()
    # One chapter→module→course join covers all the locale + access
    # decisions below. Previously source=true paid 1 query and source=false
    # paid 2, all to the same join.
    ctx = resolve_chapter_locale_context(db, chapter_id=chapter_id, current_user=current_user)
    if source:
        if not ctx.is_owner_or_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the course owner or an admin can request source-language content",
            )
        # Phase 5e2: chapter_blocks.content column dropped — build
        # source-locale responses by re-using the resolve layer that
        # already does the cv lookups (source==display when no
        # localisation requested).
        return localize_chapter_block_rows(db, rows, display_locale=ctx.source_locale, source_locale=ctx.source_locale)
    display_locale: LocaleCode = normalize_locale(accept_language)
    return localize_chapter_block_rows(db, rows, display_locale=display_locale, source_locale=ctx.source_locale)


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
    # Phase 5e2: ``content`` column dropped. Sanitization runs before
    # the cv write so the stored text is clean.
    content = sanitize_string(data.content) if data.content else data.content
    block = ChapterBlock(
        chapter_id=chapter_id,
        block_type=data.block_type,
        order_index=data.order_index,
        quiz_id=data.quiz_id,
        assignment_id=data.assignment_id,
        file_bucket=data.file_bucket,
        file_path=data.file_path,
        file_name=data.file_name,
    )
    db.add(block)
    try:
        db.flush()
        dual_write_entity_content(
            db,
            entity_type="chapter_block",
            entity_id=str(block.id),
            fallback_locale=_course_source_locale_for_chapter(db, chapter_id),
            authored_by=teacher.id,
            texts={"content": content},
        )
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
    return _block_to_response(db, block)


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
    patch = data.model_dump(exclude_unset=True)
    # Phase 5e2: content column gone — route the (sanitised) content
    # straight to cv; all other fields setattr as before.
    content_patch = patch.pop("content", None) if "content" in patch else None
    if content_patch is not None:
        content_patch = sanitize_string(content_patch) if content_patch else content_patch
    for field, value in patch.items():
        setattr(block, field, value)
    try:
        db.flush()
        if content_patch is not None:
            dual_write_entity_content(
                db,
                entity_type="chapter_block",
                entity_id=str(block.id),
                fallback_locale=_course_source_locale_for_chapter(db, block.chapter_id),
                authored_by=teacher.id,
                texts={"content": content_patch},
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Referenced quiz or assignment no longer exists",
        ) from exc
    db.refresh(block)
    reconcile_entity_if_course_published(db, "chapter_block", block)
    return _block_to_response(db, block)


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
    # Reject the whole reorder if any submitted id doesn't belong to
    # this chapter. The previous behaviour silently dropped unmatched
    # ids and committed a partial reorder, leaving the visible order
    # of the persisted blocks inconsistent with what the teacher saw
    # in the DnD list -- and giving no signal that anything went wrong.
    missing = [str(item.id) for item in items if item.id not in blocks_by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot reorder: {len(missing)} block id(s) do not belong to this chapter "
                f"(or no longer exist): {', '.join(missing[:5])}" + ("..." if len(missing) > 5 else "")
            ),
        )
    for item in items:
        blocks_by_id[item.id].order_index = item.order_index
    db.commit()
    # Phase 5e2: content column dropped — must resolve via cv. Use the
    # chapter's parent course source_locale; display=source is fine for
    # this teacher-only endpoint (the editor reorders source blocks).
    ctx = resolve_chapter_locale_context(db, chapter_id=chapter_id, current_user=teacher)
    rows = db.query(ChapterBlock).filter(ChapterBlock.chapter_id == chapter_id).order_by(ChapterBlock.order_index).all()
    return localize_chapter_block_rows(db, rows, display_locale=ctx.source_locale, source_locale=ctx.source_locale)
