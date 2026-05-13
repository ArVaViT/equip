from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Mirrors the ``chapters_chapter_type_check`` CHECK in Postgres. ``video`` /
# ``audio`` / ``mixed`` / ``content`` were collapsed into block-based
# ``reading`` by migration 024 — block rows carry the content shape instead.
CHAPTER_TYPES = Literal["reading", "quiz", "exam", "assignment"]


class ChapterBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    order_index: int = 0
    chapter_type: CHAPTER_TYPES = "reading"
    requires_completion: bool = False
    is_locked: bool = False


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    order_index: int | None = None
    chapter_type: CHAPTER_TYPES | None = None
    requires_completion: bool | None = None
    is_locked: bool | None = None


class ChapterResponse(ChapterBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    module_id: str


class ChapterSummary(BaseModel):
    """Chapter fields for list responses — identical to ``ChapterResponse``
    now that no body content lives on the chapter row. Kept as a separate
    type so future slimming (e.g. dropping ``chapter_type``) is easy."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    module_id: str
    title: str
    order_index: int = 0
    chapter_type: CHAPTER_TYPES = "reading"
    requires_completion: bool = False
    is_locked: bool = False


class ModuleBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    order_index: int = 0
    due_date: datetime | None = None


class ModuleCreate(ModuleBase):
    pass


class ModuleUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    order_index: int | None = None
    due_date: datetime | None = None


class ModuleResponse(ModuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    chapters: list[ChapterResponse] = []


class ModuleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    title: str
    description: str | None = None
    order_index: int = 0
    due_date: datetime | None = None
    chapters: list[ChapterSummary] = []


class CourseBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=10_000)
    image_url: str | None = Field(None, max_length=2048)


class CourseCreate(CourseBase):
    pass


class CourseUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=10_000)
    image_url: str | None = Field(None, max_length=2048)
    status: Literal["draft", "published"] | None = None
    # ADR-010: course access mode controls who can ENROLL (public allows
    # solo self-enroll; institute is admin-invite only). Only admins should
    # PATCH this — the route's permission check enforces that.
    access_mode: Literal["public", "institute"] | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None


class CourseResponse(CourseBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str = "draft"
    # Controls the enroll button on the catalog: ``public`` shows
    # "Записаться", ``institute`` shows "Доступно только по приглашению".
    access_mode: Literal["public", "institute"] = "public"
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    modules: list[ModuleResponse] = []


class CourseSummary(CourseBase):
    """Catalog / list-view course. Kept as a separate shape from
    ``CourseResponse`` so that if we later decide to, say, omit modules/
    chapters from list responses entirely, we can do that in one place.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str = "draft"
    access_mode: Literal["public", "institute"] = "public"
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    modules: list[ModuleSummary] = []


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: UUID
    course_id: str
    cohort_id: UUID | None = None
    enrolled_at: datetime
    progress: int
    course: CourseResponse | None = None


class EnrollmentSummaryResponse(BaseModel):
    """Enrollment for list views — embeds the slim CourseSummary."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: UUID
    course_id: str
    cohort_id: UUID | None = None
    enrolled_at: datetime
    progress: int
    course: CourseSummary | None = None


class CourseTranslationResponse(BaseModel):
    """Summary returned by the manual ``POST /courses/{id}/translate`` hook.

    Mirrors ``OrchestratorReport`` from the translation service so the
    teacher UI can show "X translated, Y skipped, Z failed" without having
    to re-shape the payload on the client.
    """

    translated: int = 0
    skipped: int = 0
    failed: int = 0
    enabled: bool = True
