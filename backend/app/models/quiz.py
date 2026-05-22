import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Quiz(Base):
    __tablename__ = "quizzes"
    __table_args__ = (Index("ix_quizzes_chapter_id", "chapter_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    quiz_type: Mapped[str] = mapped_column(String(20), default="quiz", server_default="quiz")
    max_attempts: Mapped[int | None] = mapped_column()
    passing_score: Mapped[int] = mapped_column(default=70)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.order_index",
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (Index("ix_quiz_questions_quiz_id_order", "quiz_id", "order_index"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"))
    question_text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(20), default="multiple_choice")
    order_index: Mapped[int] = mapped_column(default=0)
    points: Mapped[int] = mapped_column(default=1)
    # Only meaningful for ``essay`` — UX hint rendered on the student's textarea.
    min_words: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")
    options: Mapped[list["QuizOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuizOption.order_index",
    )


class QuizOption(Base):
    __tablename__ = "quiz_options"
    __table_args__ = (Index("ix_quiz_options_question_id", "question_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quiz_questions.id", ondelete="CASCADE"))
    option_text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(default=False)
    order_index: Mapped[int] = mapped_column(default=0)

    question: Mapped["QuizQuestion"] = relationship(back_populates="options")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        Index("ix_quiz_attempts_user_quiz", "user_id", "quiz_id"),
        Index("ix_quiz_attempts_quiz_id", "quiz_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    score: Mapped[int | None] = mapped_column()
    max_score: Mapped[int | None] = mapped_column()
    passed: Mapped[bool | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    answers: Mapped[list["QuizAnswer"]] = relationship(back_populates="attempt", cascade="all, delete-orphan")


class QuizExtraAttempt(Base):
    __tablename__ = "quiz_extra_attempts"
    __table_args__ = (Index("ix_quiz_extra_attempts_quiz_user", "quiz_id", "user_id", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    extra_attempts: Mapped[int] = mapped_column(default=1)
    # granted_by stays nullable=False but intentionally has no FK: we never want
    # a student's extra-attempt grant to disappear because an admin account was
    # later deleted. Keep as a loose reference.
    granted_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (
        Index("ix_quiz_answers_attempt_id", "attempt_id"),
        Index("ix_quiz_answers_question_id", "question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quiz_attempts.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quiz_questions.id", ondelete="CASCADE"))
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("quiz_options.id", ondelete="SET NULL"))
    text_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column()
    points_earned: Mapped[int] = mapped_column(default=0)
    # Teacher feedback for manually-graded answers; null until a teacher
    # actually grades it (see PATCH /quizzes/answers/{id}).
    grader_comment: Mapped[str | None] = mapped_column(Text)
    # When this answer was last graded. ``NULL`` means "still pending a
    # teacher's manual review" — used by the pending-answer queue to
    # distinguish unmodified open-ended answers from ones a teacher
    # legitimately scored at 0 with no comment (see migration
    # 20260515153526_quiz_answers_graded_at.sql). Auto-graded answer
    # types (multiple_choice / true_false) are stamped at submit time
    # because they're scored deterministically; only open-ended answers
    # ever have ``graded_at IS NULL`` in steady state.
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempt: Mapped["QuizAttempt"] = relationship(back_populates="answers")
