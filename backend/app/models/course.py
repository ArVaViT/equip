import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.enrollment import Enrollment


class TSVector(TypeDecorator):
    """PostgreSQL TSVECTOR that falls back to TEXT on non-PG dialects (SQLite)."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import TSVECTOR

            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


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
    title: Mapped[str] = mapped_column()
    description: Mapped[str | None] = mapped_column()
    image_url: Mapped[str | None] = mapped_column()
    status: Mapped[str] = mapped_column(default="draft")
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

    search_vector: Mapped[str | None] = mapped_column(TSVector())

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

    def __repr__(self) -> str:
        return f"<Course id={self.id!r} title={self.title!r}>"


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
    title: Mapped[str] = mapped_column()
    description: Mapped[str | None] = mapped_column()
    order_index: Mapped[int] = mapped_column(default=0)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped["Course"] = relationship(back_populates="modules")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="Chapter.order_index",
    )

    def __repr__(self) -> str:
        return f"<Module id={self.id!r} title={self.title!r} course_id={self.course_id!r}>"


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
    chapter_type: Mapped[str] = mapped_column(default="reading")
    requires_completion: Mapped[bool] = mapped_column(default=False)
    is_locked: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    module: Mapped["Module"] = relationship(back_populates="chapters")

    def __repr__(self) -> str:
        return f"<Chapter id={self.id!r} title={self.title!r} module_id={self.module_id!r}>"
