from datetime import datetime
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
    quiz_weight: int = Field(..., ge=0, le=100)
    assignment_weight: int = Field(..., ge=0, le=100)
    participation_weight: int = Field(..., ge=0, le=100)

    @model_validator(mode="after")
    def weights_must_sum_to_100(self):
        total = self.quiz_weight + self.assignment_weight + self.participation_weight
        if total != 100:
            raise ValueError(f"Weights must sum to 100, got {total}")
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
