from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ``video`` / ``audio`` block types were collapsed into ``text`` by migration
# 025 — the rich text editor embeds them via its toolbar so the separate block
# kinds were pure duplication.
BLOCK_TYPES = Literal["text", "quiz", "assignment", "file"]

# File-bucket allowlist. The signed-URL fetch trusts whatever bucket name the
# block row carries, so without this gate a teacher could plant a block with
# ``file_bucket='avatars'`` and mint signed URLs against another tenant's
# objects. ``course-materials`` is the only bucket the upload path actually
# writes to.
_ALLOWED_FILE_BUCKETS = frozenset({"course-materials"})


def _validate_file_bucket(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in _ALLOWED_FILE_BUCKETS:
        raise ValueError(f"file_bucket must be one of: {sorted(_ALLOWED_FILE_BUCKETS)}")
    return value


def _validate_file_path(value: str | None) -> str | None:
    """Reject path-traversal attempts and absolute paths.

    Per-chapter scope is enforced at the route layer (the upload sets
    the path to ``{chapter_id}/{ts}-{name}``), but defense-in-depth at
    the schema rejects any ``..`` segment and any leading ``/``
    regardless of how the path was obtained.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("/") or stripped.startswith("\\"):
        raise ValueError("file_path must be relative (no leading slash)")
    # Split on both unix + windows separators and check each segment.
    segments = stripped.replace("\\", "/").split("/")
    if any(segment in ("..", ".") for segment in segments):
        raise ValueError("file_path must not contain '..' or '.' segments")
    return value


class BlockCreate(BaseModel):
    block_type: BLOCK_TYPES
    order_index: int = Field(0, ge=0)
    content: str | None = Field(None, max_length=500_000)
    quiz_id: str | None = Field(None, max_length=36)
    assignment_id: str | None = Field(None, max_length=36)
    file_bucket: str | None = Field(None, max_length=50)
    file_path: str | None = Field(None, max_length=2048)
    file_name: str | None = Field(None, max_length=255)

    @field_validator("file_bucket")
    @classmethod
    def _check_bucket(cls, v: str | None) -> str | None:
        return _validate_file_bucket(v)

    @field_validator("file_path")
    @classmethod
    def _check_path(cls, v: str | None) -> str | None:
        return _validate_file_path(v)


class BlockUpdate(BaseModel):
    block_type: BLOCK_TYPES | None = None
    order_index: int | None = Field(None, ge=0)
    content: str | None = Field(None, max_length=500_000)
    quiz_id: str | None = Field(None, max_length=36)
    assignment_id: str | None = Field(None, max_length=36)
    file_bucket: str | None = Field(None, max_length=50)
    file_path: str | None = Field(None, max_length=2048)
    file_name: str | None = Field(None, max_length=255)

    @field_validator("file_bucket")
    @classmethod
    def _check_bucket(cls, v: str | None) -> str | None:
        return _validate_file_bucket(v)

    @field_validator("file_path")
    @classmethod
    def _check_path(cls, v: str | None) -> str | None:
        return _validate_file_path(v)


class BlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chapter_id: str
    block_type: str
    order_index: int
    content: str | None = None
    quiz_id: UUID | None = None
    assignment_id: UUID | None = None
    file_bucket: str | None = None
    file_path: str | None = None
    file_name: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class BlockReorderItem(BaseModel):
    id: UUID
    order_index: int
