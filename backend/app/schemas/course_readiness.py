"""Pydantic models that mirror ``app.services.course_readiness`` for
the public API contract.

We keep two separate type universes — dataclasses in the service for
internal logic, Pydantic models for the wire format — so the service
function stays trivially unit-testable without a Pydantic instance and
the schema layer owns OpenAPI doc strings, ``Literal`` constraints,
and (when we add it) JSON-schema validation on the way in.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "recommended", "polish"]
SubjectType = Literal["course", "module", "chapter", "quiz", "assignment"]
ActionType = Literal[
    "set_description",
    "set_cover_image",
    "open_enrollment",
    "add_module",
    "open_module",
    "open_chapter",
    "open_quiz",
    "open_assignment",
    "open_grading_weights",
]


class ReadinessSubject(BaseModel):
    """The entity a check refers to (when it isn't course-level)."""

    type: SubjectType
    id: str
    title: str


class ReadinessAction(BaseModel):
    """Hint to the frontend about how to deep-link to a fix."""

    type: ActionType
    params: dict[str, str] = Field(default_factory=dict)


class ReadinessCheck(BaseModel):
    """One verdict — passed or failing — for a single rule."""

    id: str = Field(..., description="Stable check identifier (slug or slug:entity_id)")
    severity: Severity
    passed: bool
    message_key: str = Field(..., description="i18n key the frontend looks up to render the message")
    subject: ReadinessSubject | None = None
    action: ReadinessAction | None = None


class ReadinessReport(BaseModel):
    """Aggregated readiness for a course."""

    course_id: str
    total: int = Field(..., description="Total number of checks in the report")
    passing: int = Field(..., description="Number of checks that passed")
    critical_failing: int = Field(
        ...,
        description="Number of failing checks at ``critical`` severity. If > 0 the publish flow should confirm before promoting the course.",
    )
    score: int = Field(..., ge=0, le=100, description="Percent of checks passing")
    checks: list[ReadinessCheck]
