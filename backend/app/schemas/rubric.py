from uuid import UUID

from pydantic import BaseModel, Field


class RubricLevelIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    #: Bounded for the same reason the CHECK constraint is: one criterion worth
    #: 5000 silently swamps every other one, and the mark still looks arithmetically
    #: fine.
    points: int = Field(0, ge=0, le=1000)
    description: str | None = Field(None, max_length=2000)


class RubricCriterionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=2000)
    #: At least two: a criterion with one level is not a judgement, it is a
    #: label. Capped so one rubric cannot become a form with fifty radio
    #: buttons per row.
    levels: list[RubricLevelIn] = Field(..., min_length=2, max_length=10)


class RubricCreate(BaseModel):
    """A rubric arrives whole.

    Criteria and levels in one call rather than three endpoints and a
    client-side transaction: a rubric that exists with two of its four criteria
    is a marking standard nobody agreed to, and it is the state every failed
    save would leave behind.
    """

    course_id: str = Field(..., max_length=36)
    title: str = Field(..., min_length=1, max_length=300)
    criteria: list[RubricCriterionIn] = Field(..., min_length=1, max_length=20)


class RubricLevelOut(BaseModel):
    id: UUID
    label: str
    points: int
    description: str | None = None
    order_index: int = 0


class RubricCriterionOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    order_index: int = 0
    levels: list[RubricLevelOut] = []


class RubricResponse(BaseModel):
    """The grid, as both roles see it. The student's copy is not a summary."""

    id: UUID
    course_id: str
    title: str
    #: The sum of the best level of each criterion — and the assignment's
    #: maximum, because there cannot be two of those.
    max_score: int
    criteria: list[RubricCriterionOut] = []


class RubricMarkIn(BaseModel):
    criterion_id: UUID
    #: The decision. Points are read from the level, never sent by the client —
    #: a mark that carries its own number is a number the server has to trust.
    level_id: UUID
    comment: str | None = Field(None, max_length=2000)


class RubricMarksRequest(BaseModel):
    marks: list[RubricMarkIn] = Field(..., min_length=1, max_length=20)
    #: Feedback on the whole piece of work. Omitted leaves whatever is there —
    #: an autosave of one criterion must not wipe what the teacher already wrote.
    feedback: str | None = Field(None, max_length=5000)


class RubricMarkOut(BaseModel):
    criterion_id: UUID
    level_id: UUID
    points: int
    comment: str | None = None


class SubmissionRubricResponse(BaseModel):
    rubric: RubricResponse | None = None
    marks: list[RubricMarkOut] = []
    #: ``None`` when the assignment has no rubric at all, so a client can tell
    #: «no rubric here» from «rubric, nothing marked yet» — which are different
    #: screens.
    earned: int | None = None
    out_of: int | None = None
