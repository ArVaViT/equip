from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GradeUpsert(BaseModel):
    grade: str | None = Field(None, max_length=10)
    comment: str | None = Field(None, max_length=5000)


class GradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    course_id: str
    cohort_id: UUID | None = None
    grade: str | None = None
    comment: str | None = None
    graded_by: UUID | None = None
    graded_at: datetime
    updated_at: datetime | None = None


class GradingConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quiz_weight: int
    assignment_weight: int
    participation_weight: int


class GradingConfigUpdate(BaseModel):
    """Course weights on the write path — two categories, never three.

    "Participation" was retired as a weighted category (D5). The field is still
    accepted because browsers that loaded the SPA before the change keep PUTing
    the old 30/50/20 shape, and answering a stale tab with a 422 would strand a
    teacher mid-edit with an error they cannot act on. Instead the server folds
    the participation share into the two real categories and stores 0, applying
    the same two rules as the migration so a stale tab and a fresh one converge:

    * the untouched platform default 30/50/20 becomes the new default 40/60 —
      not the 38/62 proportional arithmetic would give. Nobody chose 30/50/20,
      and carrying that non-decision forward would leave a school with two
      different splits and a number no teacher can reproduce on paper;
    * weights a teacher actually set keep their ratio.
    """

    quiz_weight: int = Field(..., ge=0, le=100)
    assignment_weight: int = Field(..., ge=0, le=100)
    participation_weight: int = Field(0, ge=0, le=100)

    @model_validator(mode="after")
    def normalize_and_validate(self):
        total = self.quiz_weight + self.assignment_weight + self.participation_weight
        if total != 100:
            raise ValueError(f"Weights must sum to 100, got {total}")

        if self.participation_weight:
            base = self.quiz_weight + self.assignment_weight
            if (self.quiz_weight, self.assignment_weight, self.participation_weight) == (30, 50, 20):
                # The old platform default — a non-decision, not a choice.
                self.quiz_weight, self.assignment_weight = 40, 60
            elif base == 0:
                # Nothing to fold into; inventing a ratio would be arbitrary.
                self.quiz_weight, self.assignment_weight = 40, 60
            else:
                # Ties round away from zero, matching Postgres `round()` in the
                # migration rather than Python's round-half-to-even.
                self.quiz_weight = int(
                    (Decimal(self.quiz_weight * 100) / Decimal(base)).quantize(Decimal("1"), ROUND_HALF_UP)
                )
                self.assignment_weight = 100 - self.quiz_weight
            self.participation_weight = 0

        return self


class GradeBreakdown(BaseModel):
    quiz_avg: float
    quiz_weighted: float
    assignment_avg: float
    assignment_weighted: float
    participation_pct: float
    participation_weighted: float
    final_score: float
    letter_grade: str


class StudentCalculatedGrade(BaseModel):
    student_id: str
    student_name: str | None
    student_email: str
    breakdown: GradeBreakdown
    manual_grade: str | None = None


class GradeSummaryResponse(BaseModel):
    course_id: str
    config: GradingConfigResponse
    students: list[StudentCalculatedGrade]
    class_average: float
