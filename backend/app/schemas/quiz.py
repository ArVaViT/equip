from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QuizOptionCreate(BaseModel):
    option_text: str = Field(..., max_length=500)
    is_correct: bool = False
    order_index: int = 0


class QuizOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    option_text: str
    is_correct: bool
    order_index: int


class QuizOptionStudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    option_text: str
    order_index: int


QuestionType = Literal["multiple_choice", "true_false", "short_answer", "essay"]


class QuizQuestionCreate(BaseModel):
    # 4000 chars keeps room for full essay prompts (rubrics, reading refs,
    # formatting requirements). The historical 1000-char cap blocked
    # long-form essay exam questions.
    question_text: str = Field(..., min_length=1, max_length=4000)
    question_type: QuestionType = "multiple_choice"
    order_index: int = Field(0, ge=0)
    points: int = Field(1, ge=1, le=100)
    # Only meaningful for ``essay``; acts as a soft hint on the student's
    # textarea ("write at least N words"). Kept nullable so ``short_answer``
    # questions stay unconstrained.
    min_words: int | None = Field(None, ge=1, le=10_000)
    options: list[QuizOptionCreate] = Field(default_factory=list, max_length=20)


class QuizQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_text: str
    question_type: str
    order_index: int
    points: int
    min_words: int | None = None
    options: list[QuizOptionResponse] = []


class QuizQuestionStudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_text: str
    question_type: str
    order_index: int
    points: int
    min_words: int | None = None
    options: list[QuizOptionStudentResponse] = []


class QuizCreate(BaseModel):
    # Chapter ids are UUIDs (36 chars). Cap at the schema layer so a crafted
    # 1 MB string is rejected by Pydantic before the route runs ``verify_chapter_owner``
    # against it. Matches the bounds already on ``AssignmentCreate.chapter_id``
    # and ``CohortCourseAttach.course_id``.
    chapter_id: str = Field(..., min_length=1, max_length=36)
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    quiz_type: Literal["quiz", "exam"] = "quiz"
    max_attempts: int | None = Field(None, ge=1, le=10)
    passing_score: int = Field(70, ge=0, le=100)
    questions: list[QuizQuestionCreate] = Field(default_factory=list, max_length=100)


class QuizUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    quiz_type: Literal["quiz", "exam"] | None = None
    max_attempts: int | None = Field(None, ge=1, le=10)
    passing_score: int | None = Field(None, ge=0, le=100)


class QuizResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chapter_id: str
    title: str
    description: str | None = None
    quiz_type: Literal["quiz", "exam"] = "quiz"
    max_attempts: int | None = None
    passing_score: int
    created_at: datetime
    updated_at: datetime | None = None
    questions: list[QuizQuestionResponse] = []


class QuizStudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chapter_id: str
    title: str
    description: str | None = None
    quiz_type: Literal["quiz", "exam"] = "quiz"
    max_attempts: int | None = None
    passing_score: int
    questions: list[QuizQuestionStudentResponse] = []


class QuizSubmitAnswer(BaseModel):
    question_id: UUID
    selected_option_id: UUID | None = None
    text_answer: str | None = Field(None, max_length=10_000)


class QuizSubmitRequest(BaseModel):
    answers: list[QuizSubmitAnswer] = Field(..., min_length=1, max_length=200)


class QuizAnswerResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    question_id: UUID
    selected_option_id: UUID | None = None
    text_answer: str | None = None
    is_correct: bool | None = None
    points_earned: int = 0
    grader_comment: str | None = None
    correct_option_id: UUID | None = None


class QuizAnswerGradeRequest(BaseModel):
    """Teacher-facing payload for grading a single open-ended answer."""

    points_earned: int = Field(..., ge=0, le=100)
    grader_comment: str | None = Field(None, max_length=5_000)


class PendingAnswerInfo(BaseModel):
    """Flat record for the teacher's "pending manual grading" list."""

    model_config = ConfigDict(from_attributes=True)

    answer_id: UUID
    attempt_id: UUID
    question_id: UUID
    question_text: str
    question_type: str
    max_points: int
    min_words: int | None = None
    text_answer: str | None = None
    points_earned: int
    grader_comment: str | None = None
    student_id: UUID
    student_name: str | None = None
    student_email: str
    submitted_at: datetime | None = None


class QuizAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quiz_id: UUID
    user_id: UUID
    score: int | None = None
    max_score: int | None = None
    passed: bool | None = None
    started_at: datetime
    completed_at: datetime | None = None
    answers: list[QuizAnswerResult] = []


class GrantExtraAttemptsRequest(BaseModel):
    user_id: UUID
    extra_attempts: int = Field(..., ge=1, le=10)


class ExtraAttemptsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quiz_id: UUID
    user_id: UUID
    extra_attempts: int
    granted_by: UUID
    created_at: datetime
