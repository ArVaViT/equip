"""Cohort schemas — top-level admin entity (ADR-010).

A cohort is a named batch of students that takes some set of courses
together over a date window. The director creates an empty cohort,
then independently attaches courses (via ``cohort_courses``) and
students (via ``enrollments`` with ``cohort_id`` set).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas._request import RequestModel

# Mirrors the Postgres ``cohorts_status_check`` CHECK constraint and the
# SQLAlchemy ``CohortStatus`` enum + ``CheckConstraint`` in
# ``app/models/cohort.py``. Single literal here keeps both write and read
# schemas pointing at the same 4-tuple instead of repeating it inline.
CohortStatus = Literal["upcoming", "active", "completed", "archived"]


def _validate_cohort_dates(
    *,
    start_date: datetime | None,
    end_date: datetime | None,
    enrollment_start: datetime | None,
    enrollment_end: datetime | None,
) -> None:
    """Enforce the chronological invariants every cohort must satisfy:

    ``enrollment_start ≤ enrollment_end ≤ start_date < end_date``

    Each pair is only checked when both sides are present (``CohortUpdate``
    is a patch — most fields are optional). A teacher / admin shouldn't
    be able to POST a window that ends before it starts or an enrollment
    period that closes after the cohort begins.
    """
    if start_date is not None and end_date is not None and start_date >= end_date:
        raise ValueError("end_date must be after start_date")
    if enrollment_start is not None and enrollment_end is not None and enrollment_start > enrollment_end:
        raise ValueError("enrollment_end must be on or after enrollment_start")
    if enrollment_end is not None and start_date is not None and enrollment_end > start_date:
        raise ValueError("enrollment_end must be on or before start_date")


class CohortCreate(RequestModel):
    """Inputs for creating an empty cohort. Courses and students are
    attached via the junction endpoints; this body is just the metadata."""

    name: str = Field(..., min_length=1, max_length=200)
    start_date: datetime
    end_date: datetime
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    max_students: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def _check_dates(self) -> "CohortCreate":
        _validate_cohort_dates(
            start_date=self.start_date,
            end_date=self.end_date,
            enrollment_start=self.enrollment_start,
            enrollment_end=self.enrollment_end,
        )
        return self


class CohortUpdate(RequestModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    start_date: datetime | None = None
    end_date: datetime | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    # ``upcoming → active → completed`` is the intended forward path.
    # Going back from ``completed`` is prevented at the route layer
    # (see ``update_cohort`` in ``api/v1/cohorts.py``). ``archived`` is in
    # the type for mirror-completeness with the DB CHECK constraint, but
    # the route layer should still reject it for a regular UPDATE — only
    # a dedicated admin "archive cohort" endpoint should set it.
    status: CohortStatus | None = None
    max_students: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def _check_dates(self) -> "CohortUpdate":
        _validate_cohort_dates(
            start_date=self.start_date,
            end_date=self.end_date,
            enrollment_start=self.enrollment_start,
            enrollment_end=self.enrollment_end,
        )
        return self


class CohortResponse(BaseModel):
    """Cohort overview. ``course_ids`` and ``student_count`` are computed
    fields populated by the route handler from the junction + enrollments
    tables — they are not stored on the model itself."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    start_date: datetime
    end_date: datetime
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    status: CohortStatus
    max_students: int | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None

    # Computed:
    course_ids: list[str] = Field(default_factory=list)
    student_count: int = 0


class CohortCourseAttach(RequestModel):
    """POST /cohorts/{id}/courses — attach a course to a cohort."""

    # Course ids are UUIDs (36 chars). The bound prevents a crafted
    # 1 MB string from making it as far as the SQL layer where it'd
    # waste a round trip before the FK check rejected it.
    course_id: str = Field(..., min_length=1, max_length=36)


class CohortStudentAdd(RequestModel):
    """POST /cohorts/{id}/students — add a student to a cohort.

    Either ``user_id`` (existing platform user) or ``email`` (invite-by-
    email, the backend resolves to user). Exactly one must be set.
    """

    user_id: UUID | None = None
    email: EmailStr | None = None


class CohortStudentCourseProgress(BaseModel):
    """Per-course enrollment summary nested inside a cohort student row."""

    enrollment_id: str
    enrolled_at: str | None = None
    progress: int


class CohortStudentRow(BaseModel):
    """One row in the per-cohort students listing — the student's identity
    plus a per-course enrollment summary. Used by the cohort overview
    page. Matches the exact shape returned by
    ``GET /cohorts/{id}/students`` (carries PII: full_name + email, so the
    response is validated on the way out)."""

    user_id: str
    full_name: str | None = None
    email: str
    # This cohort spans N courses, so a student has up to N enrollments,
    # keyed by course_id.
    per_course: dict[str, CohortStudentCourseProgress] = Field(default_factory=dict)
