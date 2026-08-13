from datetime import datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssignmentCreate(BaseModel):
    chapter_id: str = Field(..., max_length=36)
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=50_000)
    max_score: int = Field(100, ge=1, le=10000)
    due_date: datetime | None = None


class AssignmentUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=50_000)
    max_score: int | None = Field(None, ge=1, le=10000)
    due_date: datetime | None = None


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chapter_id: str
    title: str
    description: str | None = None
    max_score: int
    due_date: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SubmissionDeclarationIn(BaseModel):
    """What the student says about this piece of work (§4.2).

    ``statement`` is the text they were actually shown, sent back so what is
    stored is what was on their screen rather than what a catalogue says today.
    """

    ai_use: Literal["none", "assisted"]
    statement: str = Field(..., min_length=1, max_length=4000)
    #: Their own sentence about what they used it for, where the course asks
    #: for disclosure. It tells a teacher more than any detector would.
    note: str | None = Field(None, max_length=2000)


class SubmissionCreate(BaseModel):
    content: str | None = Field(None, max_length=50_000)
    file_url: str | None = Field(None, max_length=2048)
    #: Required when the course has a policy to declare against. Absent on an
    #: ``ai_open`` course, where there is nothing to declare.
    declaration: SubmissionDeclarationIn | None = None

    @field_validator("file_url")
    @classmethod
    def _enforce_https_scheme(cls, value: str | None) -> str | None:
        """Reject anything but a fully-qualified ``https://`` URL.

        A student-supplied URL is rendered by the teacher as
        ``<a href={file_url} target="_blank">`` in the grader UI.
        Allowing ``javascript:`` / ``data:`` / ``vbscript:`` would
        execute attacker-controlled code in the teacher's session the
        moment they click; ``rel=noopener`` does not defuse
        ``javascript:``. We also reject bare ``http://`` because
        every legitimate storage origin in this stack is HTTPS, and
        accepting mixed-content links would surface a browser warning
        more often than it would help.
        """
        if value is None or not value.strip():
            return None
        parsed = urlparse(value.strip())
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValueError("file_url must be an https:// URL")
        return value


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assignment_id: UUID
    student_id: UUID
    content: str | None = None
    file_url: str | None = None
    submitted_at: datetime
    status: str
    grade: int | None = None
    feedback: str | None = None
    graded_by: UUID | None = None
    graded_at: datetime | None = None


class GradeSubmissionRequest(BaseModel):
    # ``le`` mirrors ``max_score`` (≤10000) as a schema-level sanity ceiling.
    # The route still rejects ``grade > the assignment's own max_score``; this
    # just stops an absurd value being accepted by the schema alone.
    grade: int = Field(..., ge=0, le=10000)
    feedback: str | None = Field(None, max_length=5000)
    # Must stay a subset of the DB CHECK on ``assignment_submissions.status``
    # (``submitted|graded|returned``). ``pending`` used to be accepted here
    # but writing it would trip the CHECK on Postgres and return a 409 to the
    # teacher. ``returned`` is what the UI sends for "return for revision".
    status: Literal["graded", "returned"] = "graded"
