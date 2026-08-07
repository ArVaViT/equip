import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.enrollment import Enrollment


class CourseStatus(enum.StrEnum):
    """Publication state of a course.

    ``draft`` — only the course owner + admins can see it. Self-enrollment
    is blocked.
    ``published`` — visible in the public catalog; students can enroll.

    Stored as a raw string in Postgres (CHECK-constrained); the enum
    just gives Python code a single source of truth so a typo in
    ``"publshed"`` is caught at the call site instead of silently
    excluding rows from queries.
    """

    DRAFT = "draft"
    PUBLISHED = "published"


class CourseAccessMode(enum.StrEnum):
    """Whether a published course accepts solo self-enrollment.

    ``public`` — anyone can enroll within the course's enrollment window.
    ``institute`` — only admins add students via the cohort flow
    (see ADR-010).
    """

    PUBLIC = "public"
    INSTITUTE = "institute"


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        Index("ix_courses_created_by", "created_by"),
        Index(
            "ix_courses_status_created_at",
            "status",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_courses_access_mode", "access_mode"),
        Index(
            "ix_courses_created_by_active",
            "created_by",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "quiz_weight + assignment_weight + participation_weight = 100",
            name="ck_courses_weights_sum_100",
        ),
        CheckConstraint("participation_weight = 0", name="ck_courses_participation_retired"),
        CheckConstraint(
            "grading_scheme IN ('pass_fail', 'percent', 'five_point', 'letter')",
            name="courses_grading_scheme_check",
        ),
        CheckConstraint("pass_threshold >= 0 AND pass_threshold <= 100", name="courses_pass_threshold_check"),
        CheckConstraint("academic_hours > 0", name="courses_academic_hours_check"),
        # D8.1: the five-point «3» line cannot sit above 75 or the
        # «удовлетворительно» band becomes unreachable. Backstop for any write
        # path that bypasses the paired scheme+threshold endpoint.
        CheckConstraint(
            "grading_scheme <> 'five_point' OR pass_threshold <= 75",
            name="ck_courses_scheme_threshold",
        ),
        # Mirror prod CHECK constraints (catalog status, enroll access mode, authoring locale).
        CheckConstraint("status IN ('draft', 'published')", name="chk_courses_status"),
        CheckConstraint("access_mode IN ('public', 'institute')", name="courses_access_mode_check"),
        CheckConstraint("source_locale IN ('ru', 'en')", name="courses_source_locale_check"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    image_url: Mapped[str | None] = mapped_column()
    status: Mapped[str] = mapped_column(default=CourseStatus.DRAFT)
    # Access mode controls who can ENROLL in the course (separate from
    # status which controls whether it's published in the catalog at all).
    # See ADR-010 in equipbible-docs/product/decisions/ — institute-mode
    # courses are visible but solo-enrollment is gated to admin.
    access_mode: Mapped[str] = mapped_column(default="public", server_default="public")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    enrollment_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrollment_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    quiz_weight: Mapped[int] = mapped_column(default=40, server_default="40")
    assignment_weight: Mapped[int] = mapped_column(default=60, server_default="60")
    # Retired as a weighted category (D5) — pinned to 0 everywhere: DB CHECK,
    # these defaults, and the API schema. It duplicated `enrollments.progress`
    # and counted every passed quiz twice. Completion is the attendance gate;
    # the column survives only for schema compatibility.
    participation_weight: Mapped[int] = mapped_column(default=0, server_default="0")

    # How this course is graded (D1). Four presets, never free-form: teachers
    # pick one, only the institution edits the bands behind them
    # (``org_settings.grade_bands``). New courses inherit the school default.
    grading_scheme: Mapped[str] = mapped_column(default="letter", server_default="letter")
    # The course-result line for the band schemes — percent / five_point /
    # letter. Distinct from ``quizzes.passing_score``, which gates chapter
    # completion; D3 keeps the two from silently disagreeing. Ignored by
    # ``pass_fail``, whose rule is completion-native (D2).
    pass_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("70"), server_default="70")
    # «Объём в часах» printed on the ведомость and the transcript. Nullable —
    # only schools issuing hour-bearing documents fill it in.
    academic_hours: Mapped[int | None] = mapped_column()

    # Authoring language for this course's content. Phase 5e-g moved
    # every translatable string into ``content_versions`` keyed by
    # ``(entity_type, entity_id, field, locale)``; the legacy
    # ``content_translations`` overlay table was dropped in 5aj. The
    # ``source_locale`` here is what the read resolver uses as the
    # display→source→any-locale fallback target so a student in EN
    # never sees a blank screen when only the RU row exists yet.
    source_locale: Mapped[str] = mapped_column(default="ru", server_default="ru")

    # ``order_by`` guarantees deterministic ordering whenever the relationship is
    # accessed, including via ``joinedload`` in ``get_course``. Without it
    # Postgres returns rows in whatever order the query plan chose, which
    # surfaced on prod as chapters shown in reverse before the explicit
    # ``order_index`` ordering was added.
    modules: Mapped[list["Module"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Module.order_index",
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="course", cascade="all, delete-orphan")

    # ``title`` and ``description`` live in ``content_versions`` (Phase 5g).
    # Read paths attach the resolved text as runtime attributes via
    # ``populate_spine_texts``; the ``__init__`` overload accepts the same
    # kwargs so existing test fixtures and write paths keep their shape.
    # Accessing ``course.title`` on an un-hydrated instance raises
    # ``AttributeError`` — that's a feature, not a bug: it surfaces
    # missing-hydration bugs at the call site instead of silently rendering
    # an empty string into a response. Every route handler in
    # ``app/api/v1`` either threads cv-aware response builders or invokes
    # ``populate_spine_texts(db, [course])`` before serialising.

    def __init__(self, **kwargs):
        title = kwargs.pop("title", None)
        description = kwargs.pop("description", None)
        super().__init__(**kwargs)
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description

    def __repr__(self) -> str:
        return f"<Course id={self.id!r}>"


class Module(Base):
    __tablename__ = "modules"
    __table_args__ = (
        Index("ix_modules_course_id_order", "course_id", "order_index"),
        Index(
            "ix_modules_course_id_order_active",
            "course_id",
            "order_index",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    # The composite ``ix_modules_course_id_order`` covers plain ``course_id``
    # lookups via its leading column, so no single-column FK index here.
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    order_index: Mapped[int] = mapped_column(default=0)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped["Course"] = relationship(back_populates="modules")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="Chapter.order_index",
    )

    # See ``Course`` for the title/description contract: cv is the only
    # store; un-hydrated access raises AttributeError on purpose.

    def __init__(self, **kwargs):
        title = kwargs.pop("title", None)
        description = kwargs.pop("description", None)
        super().__init__(**kwargs)
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description

    def __repr__(self) -> str:
        return f"<Module id={self.id!r} course_id={self.course_id!r}>"


class Chapter(Base):
    """Chapter belonging to a module.

    Bilingual storage (Phase 5e/5g divergence): unlike ``courses.title`` and
    ``modules.title`` — both dropped in Phase 5g and replaced with runtime
    attributes hydrated from ``content_versions`` — ``chapters.title``
    intentionally keeps its column. Every write path
    (``create_chapter`` / ``update_chapter`` / ``_clone_cv_rows``) writes
    the source-locale text to BOTH the column AND a ``content_versions``
    row in the same transaction, so the invariant

        ``chapter.title == cv.text WHERE entity_type='chapter' AND
        field='title' AND locale=course.source_locale AND
        superseded_by IS NULL``

    holds at every commit boundary. Reading the column is therefore
    equivalent to reading the source-locale cv row — used by editor /
    readiness / progress paths that want source text directly without
    paying for a cv lookup. Student-facing localized reads still go
    through ``Localizer.build`` in
    ``build_localized_course_response_with_tree`` (which queries the cv
    overlay per-chapter) so the runtime attr is never used for non-source
    locales.

    The invariant is pinned by
    ``tests/test_chapter_column_cv_invariant.py``. Any future code that
    writes to one side without the other will break that test.
    """

    __tablename__ = "chapters"
    __table_args__ = (
        Index("ix_chapters_module_id_order", "module_id", "order_index"),
        Index(
            "ix_chapters_module_id_order_active",
            "module_id",
            "order_index",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Mirror prod: chapter type domain.
        CheckConstraint(
            "chapter_type IN ('reading', 'quiz', 'exam', 'assignment')",
            name="chapters_chapter_type_check",
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    # Covered by the composite ``ix_chapters_module_id_order`` — same reason
    # as ``Module.course_id``.
    module_id: Mapped[str] = mapped_column(ForeignKey("modules.id"))
    title: Mapped[str] = mapped_column()
    order_index: Mapped[int] = mapped_column(default=0)
    chapter_type: Mapped[str] = mapped_column(default="reading", server_default="reading")
    requires_completion: Mapped[bool] = mapped_column(default=False)
    is_locked: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    module: Mapped["Module"] = relationship(back_populates="chapters")

    def __repr__(self) -> str:
        return f"<Chapter id={self.id!r} title={self.title!r} module_id={self.module_id!r}>"
