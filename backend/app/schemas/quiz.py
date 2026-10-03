from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.schemas._request import RequestModel

# A quiz nobody can pass used to save without a word of complaint: a
# multiple-choice question with no option marked correct is graded wrong
# whatever the student picks, and an option whose text is only spaces is
# counted as untranslated and makes the whole quiz refuse to open (409).
# The teacher found out from the students. The checks below make such a
# quiz a 422 at the door.
#
# The custom ``type`` on each error is deliberate: the client translates
# the *type* (``quiz_no_correct_option`` → «отметьте правильный ответ»)
# rather than showing the English ``msg`` written here for a log.

#: Question types whose answer is one option picked from a list.
CHOICE_TYPES: frozenset[str] = frozenset({"multiple_choice", "true_false"})


def _blank(text: str | None) -> bool:
    return text is None or not text.strip()


class _HasIsCorrect(Protocol):
    is_correct: bool


def validate_answerable(question_type: str, options: Sequence[_HasIsCorrect]) -> None:
    """Refuse a question shape nobody could answer, or that a student could not take.

    One rule for every door. It was written for ``QuizQuestionCreate`` and
    nowhere else, so a question that was answerable when it was created
    could be edited into one that was not: the per-option PATCH route took
    «unmark the only right answer» without a word, and the per-question
    PATCH route turned a short answer into a multiple choice with no
    options (2026-10-03). Every route that changes a question's type or
    its options now ends by asking this the same question creation asks.

    Raises ``PydanticCustomError`` so a schema can call it from a
    validator and a route can turn it into the same 422 list the client
    already translates by ``type``.
    """
    if question_type in CHOICE_TYPES:
        if len(options) < 2:
            raise PydanticCustomError(
                "quiz_too_few_options",
                "A {question_type} question needs at least two options",
                {"question_type": question_type},
            )
        correct = sum(1 for option in options if option.is_correct)
        if correct == 0:
            raise PydanticCustomError("quiz_no_correct_option", "Exactly one option must be marked correct")
        if correct > 1:
            raise PydanticCustomError(
                "quiz_many_correct_options",
                "Only one option may be marked correct, {correct} are",
                {"correct": correct},
            )
    elif options:
        raise PydanticCustomError(
            "quiz_options_not_allowed",
            "A {question_type} question is answered in writing and has no options",
            {"question_type": question_type},
        )


class QuizOptionCreate(RequestModel):
    option_text: str = Field(..., min_length=1, max_length=500)
    is_correct: bool = False
    order_index: int = 0

    @field_validator("option_text")
    @classmethod
    def _option_text_not_blank(cls, value: str) -> str:
        if _blank(value):
            raise PydanticCustomError("quiz_option_blank", "Option text must not be blank")
        return value


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


class QuizQuestionCreate(RequestModel):
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

    @field_validator("question_text")
    @classmethod
    def _question_text_not_blank(cls, value: str) -> str:
        if _blank(value):
            raise PydanticCustomError("quiz_question_blank", "Question text must not be blank")
        return value

    @model_validator(mode="after")
    def _answerable(self) -> "QuizQuestionCreate":
        validate_answerable(self.question_type, self.options)
        return self


class QuizQuestionUpdate(RequestModel):
    """A correction to a question a class has already seen.

    Every field is optional and only what is sent is applied: a teacher
    fixing a typo sends ``question_text`` alone and nothing else moves.
    The limits mirror ``QuizQuestionCreate`` so a question cannot be
    edited into a shape it could not have been created in.

    ``options`` is deliberately absent. Editing the answer list through
    this schema would mean deleting rows, and a deleted option takes
    every ``quiz_answers.selected_option_id`` pointing at it with it —
    the student's answer becomes NULL and their graded attempt stops
    saying what they chose. Options are edited one at a time through
    ``QuizOptionUpdate``.
    """

    question_text: str | None = Field(None, min_length=1, max_length=4000)
    question_type: QuestionType | None = None
    order_index: int | None = Field(None, ge=0)
    points: int | None = Field(None, ge=1, le=100)
    min_words: int | None = Field(None, ge=1, le=10_000)

    @field_validator("question_text")
    @classmethod
    def _question_text_not_blank(cls, value: str | None) -> str | None:
        if value is not None and _blank(value):
            raise PydanticCustomError("quiz_question_blank", "Question text must not be blank")
        return value


class QuizOptionUpdate(RequestModel):
    """A correction to one answer option."""

    option_text: str | None = Field(None, min_length=1, max_length=500)
    is_correct: bool | None = None
    order_index: int | None = Field(None, ge=0)

    @field_validator("option_text")
    @classmethod
    def _option_text_not_blank(cls, value: str | None) -> str | None:
        if value is not None and _blank(value):
            raise PydanticCustomError("quiz_option_blank", "Option text must not be blank")
        return value


class QuizOptionSave(RequestModel):
    """One of a question's existing options, as it should read after the save.

    ``id`` names a row the question already has. There is no way to add or
    drop an option here, on purpose: a deleted option nulls every
    ``quiz_answers.selected_option_id`` pointing at it and a graded attempt
    stops saying what the student chose. A changed option list is a
    rebuild (``POST /quizzes/{id}/replace``), which the editor asks about.
    """

    id: UUID
    option_text: str = Field(..., min_length=1, max_length=500)
    is_correct: bool = False
    order_index: int = Field(0, ge=0)

    @field_validator("option_text")
    @classmethod
    def _option_text_not_blank(cls, value: str) -> str:
        if _blank(value):
            raise PydanticCustomError("quiz_option_blank", "Option text must not be blank")
        return value


class QuizQuestionSave(RequestModel):
    """A question and all of its options, saved in one request.

    The per-field routes (``PATCH /quizzes/questions/{id}``,
    ``PATCH /quizzes/options/{id}``) each see one row, so between two of
    them a question is legitimately half-edited — the old right answer
    unmarked, the new one not yet marked — and neither request can be
    refused for it without refusing the edit itself. So neither was
    checked, and a question could be saved with no right answer at all
    (2026-10-03). This body carries the whole question, is validated the
    way creation is, and is applied in one transaction.
    """

    question_text: str = Field(..., min_length=1, max_length=4000)
    question_type: QuestionType = "multiple_choice"
    order_index: int = Field(0, ge=0)
    points: int = Field(1, ge=1, le=100)
    min_words: int | None = Field(None, ge=1, le=10_000)
    options: list[QuizOptionSave] = Field(default_factory=list, max_length=20)

    @field_validator("question_text")
    @classmethod
    def _question_text_not_blank(cls, value: str) -> str:
        if _blank(value):
            raise PydanticCustomError("quiz_question_blank", "Question text must not be blank")
        return value

    @model_validator(mode="after")
    def _answerable(self) -> "QuizQuestionSave":
        validate_answerable(self.question_type, self.options)
        ids = [option.id for option in self.options]
        if len(set(ids)) != len(ids):
            raise PydanticCustomError("quiz_option_repeated", "An option is listed more than once")
        return self


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


class QuizOptionEditorResponse(QuizOptionStudentResponse):
    """An option as its teacher edits it: with the answer key."""

    is_correct: bool = False


class QuizQuestionEditorResponse(QuizQuestionStudentResponse):
    options: list[QuizOptionEditorResponse] = []  # type: ignore[assignment]


class QuizBody(RequestModel):
    """The whole quiz as a teacher writes it: the fields above the questions
    and the question tree. ``QuizCreate`` adds the chapter; ``QuizReplace``
    takes it from the quiz being replaced."""

    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    quiz_type: Literal["quiz", "exam"] = "quiz"
    max_attempts: int | None = Field(None, ge=1, le=10)
    #: Omit to inherit the course's pass line (D3). The two thresholds mean
    #: different things — this one gates chapter completion, the course one is
    #: the final result line — and a hardcoded 70 here silently disagreed with
    #: a course graded at 80.
    passing_score: int | None = Field(None, ge=0, le=100)
    #: At least one: a quiz with no questions cannot be taken (``submit``
    #: needs an answer) and used to save with a 201 all the same.
    questions: list[QuizQuestionCreate] = Field(..., min_length=1, max_length=100)


class QuizCreate(QuizBody):
    # Chapter ids are UUIDs (36 chars). Cap at the schema layer so a crafted
    # 1 MB string is rejected by Pydantic before the route runs ``verify_chapter_owner``
    # against it. Matches the bounds already on ``AssignmentCreate.chapter_id``
    # and ``CohortCourseAttach.course_id``.
    chapter_id: str = Field(..., min_length=1, max_length=36)


class QuizReplace(QuizBody):
    """``POST /quizzes/{id}/replace``: the quiz that takes the old one's place.

    The editor used to rebuild a quiz whose shape changed as two requests —
    create the new quiz, delete the old — and when the delete was refused
    (a student finished an attempt in between) the chapter was left with
    two quizzes: students were shown one, the grade sheet counted both
    (2026-10-03). The replacement is one transaction; the chapter is the
    old quiz's, so it is not a field here.
    """


class QuizUpdate(RequestModel):
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


class QuizEditorResponse(QuizStudentResponse):
    """The quiz editor's payload: the student shape plus which option is right.

    The editor read the student shape, which has no ``is_correct``, so every
    existing quiz opened with no answer marked — and could not be saved
    until the teacher marked all of them again from memory.
    """

    questions: list[QuizQuestionEditorResponse] = []  # type: ignore[assignment]


class QuizSubmitAnswer(RequestModel):
    question_id: UUID
    selected_option_id: UUID | None = None
    text_answer: str | None = Field(None, max_length=10_000)


class QuizSubmitRequest(RequestModel):
    answers: list[QuizSubmitAnswer] = Field(..., min_length=1, max_length=200)

    @model_validator(mode="after")
    def _one_answer_per_question(self) -> "QuizSubmitRequest":
        # Each answer was scored as it came: the right option sent five
        # times for one question earned five times its points, past the
        # maximum, and ``passed`` with it (2026-09-30 audit).
        seen: set[UUID] = set()
        for answer in self.answers:
            if answer.question_id in seen:
                raise PydanticCustomError(
                    "quiz_duplicate_answer",
                    "Question {question_id} is answered more than once",
                    {"question_id": str(answer.question_id)},
                )
            seen.add(answer.question_id)
        return self


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


class QuizAnswerGradeRequest(RequestModel):
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
    #: The attempt came in after its module's due date — the only deadline a
    #: quiz has. Derived at read time; see ``SubmissionResponse.is_late``.
    is_late: bool = False


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
    #: Completed after the module's due date. Derived at read time, never
    #: stored; an attempt still in progress is not late yet (2026-10-03).
    is_late: bool = False


class GrantExtraAttemptsRequest(RequestModel):
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
