import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, func, text
from sqlalchemy.event import listens_for
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
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    # Phase 5g: title + description columns dropped — cv is the only store.
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

    quiz_weight: Mapped[int] = mapped_column(default=30, server_default="30")
    assignment_weight: Mapped[int] = mapped_column(default=50, server_default="50")
    participation_weight: Mapped[int] = mapped_column(default=20, server_default="20")

    # Authoring language for this course's content. The original text always
    # lives on the source rows (this table, ``modules``, ``chapters``,
    # ``chapter_blocks``, ``quizzes`` …). Translations to *other* locales are
    # stored in ``content_translations`` and are looked up by entity_id +
    # field. See supabase/migrations/...add_content_translations.
    source_locale: Mapped[str] = mapped_column(default="ru", server_default="ru")

    # Phase 5g: search_vector column dropped along with title + description.
    # Catalog search now runs against content_versions via ILIKE in the
    # query layer; the FTS index + trigger are gone.

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

    # Phase 5g: ``title`` + ``description`` are runtime-only attributes
    # populated either by ``__init__`` (write path) or by
    # ``populate_spine_texts`` (read path). Class-level defaults ensure
    # ``course.title`` / ``course.description`` never raise AttributeError
    # even on a freshly-queried instance with no hydration step.
    # No type annotation: ClassVar gets in the way of per-instance
    # assignment (mypy), and a plain ``str`` annotation gets in the way
    # of SQLAlchemy's declarative table builder. Untyped class-level
    # defaults sidestep both: each instance can override via __dict__.
    title = ""
    description = None

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
    # Phase 5g: title + description columns dropped — cv is the only store.
    order_index: Mapped[int] = mapped_column(default=0)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped["Course"] = relationship(back_populates="modules")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="Chapter.order_index",
    )

    # Phase 5g: runtime-only attributes — see Course.
    # No type annotation: ClassVar gets in the way of per-instance
    # assignment (mypy), and a plain ``str`` annotation gets in the way
    # of SQLAlchemy's declarative table builder. Untyped class-level
    # defaults sidestep both: each instance can override via __dict__.
    title = ""
    description = None

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
    __tablename__ = "chapters"
    __table_args__ = (
        Index("ix_chapters_module_id_order", "module_id", "order_index"),
        Index(
            "ix_chapters_module_id_order_active",
            "module_id",
            "order_index",
            postgresql_where=text("deleted_at IS NULL"),
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


# ---------------------------------------------------------------------------
# Phase 5g: auto-hydrate Course / Module ``.title`` and ``.description``
# from content_versions whenever an instance is loaded from the database.
# This is N+1 per instance but it makes EVERY downstream consumer (route
# handlers, services, tests, relationship lazy-loads) keep working without
# scattering ``populate_spine_texts`` calls across the codebase.
# Bulk paths (catalog list, course detail) still call
# ``populate_spine_texts`` explicitly so they hit cv once for the whole
# batch instead of N times.
# ---------------------------------------------------------------------------


def _lazy_populate_spine_text(target: "Course | Module", entity_type: str) -> None:
    from sqlalchemy.orm import Session as SASession

    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    session = SASession.object_session(target)
    if session is None:
        return
    source = getattr(target, "source_locale", None) or "en"
    texts = fetch_cv_entity_texts_with_fallback(
        session,
        entity_type=entity_type,
        entity_ids=[str(target.id)],
        fields=["title", "description"],
        display_locale=source,
        source_locale=source,
    )
    target.title = texts.get((str(target.id), "title")) or ""
    target.description = texts.get((str(target.id), "description"))


@listens_for(Course, "load")
def _course_loaded(target: "Course", _context):
    # Skip if hydration already populated the instance (e.g. via
    # ``populate_spine_texts`` before this lazy-load fires).
    if target.__dict__.get("title"):
        return
    _lazy_populate_spine_text(target, "course")


# Phase 5g: removed auto-flush hook — caused recursion via record_human_version.
# Tests that need cv-seeded spine text should use the make_course_with_text /
# make_module_with_text helpers in tests/_cv_helpers.py.


@listens_for(Module, "load")
def _module_loaded(target: "Module", _context):
    if target.__dict__.get("title"):
        return
    # Modules need their parent course's source_locale; falling back to
    # the module's own ``source_locale`` is not defined. Look up the
    # parent on demand — cached because SA usually has it eager-loaded.
    from sqlalchemy.orm import Session as SASession

    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    session = SASession.object_session(target)
    if session is None:
        return
    source = session.query(Course.source_locale).filter(Course.id == target.course_id).scalar() or "en"
    texts = fetch_cv_entity_texts_with_fallback(
        session,
        entity_type="module",
        entity_ids=[str(target.id)],
        fields=["title", "description"],
        display_locale=source,
        source_locale=source,
    )
    target.title = texts.get((str(target.id), "title")) or ""
    target.description = texts.get((str(target.id), "description"))
