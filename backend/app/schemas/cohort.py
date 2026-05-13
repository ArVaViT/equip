"""Cohort schemas — top-level admin entity (ADR-010).

A cohort is a named batch of students that takes some set of courses
together over a date window. The director creates an empty cohort,
then independently attaches courses (via ``cohort_courses``) and
students (via ``enrollments`` with ``cohort_id`` set).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CohortCreate(BaseModel):
    """Inputs for creating an empty cohort. Courses and students are
    attached via the junction endpoints; this body is just the metadata."""

    name: str = Field(..., min_length=1, max_length=200)
    start_date: datetime
    end_date: datetime
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    max_students: int | None = Field(None, ge=1)


class CohortUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    start_date: datetime | None = None
    end_date: datetime | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    status: Literal["upcoming", "active", "completed"] | None = None
    max_students: int | None = Field(None, ge=1)


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
    status: str
    max_students: int | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None

    # Computed:
    course_ids: list[str] = Field(default_factory=list)
    student_count: int = 0


class CohortCourseAttach(BaseModel):
    """POST /cohorts/{id}/courses — attach a course to a cohort."""

    course_id: str = Field(..., min_length=1)


class CohortStudentAdd(BaseModel):
    """POST /cohorts/{id}/students — add a student to a cohort.

    Either ``user_id`` (existing platform user) or ``email`` (invite-by-
    email, the backend resolves to user). Exactly one must be set.
    """

    user_id: UUID | None = None
    email: str | None = None


class CohortStudentRow(BaseModel):
    """One row in the per-cohort students listing — enrollment summary
    plus the student's identity. Used by the cohort overview page."""

    user_id: UUID
    enrolled_at: datetime | None = None
    progress: int
    # Per-course rows: this cohort spans N courses, so a student has N
    # enrollments. Aggregated client-side from the per-course response.
    per_course: dict[str, dict] = Field(default_factory=dict)
