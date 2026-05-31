import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.enrollment import Enrollment


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class User(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # ``unique=True`` already creates a B-tree; a second ``index=True`` would
    # just duplicate writes. Same logic applies to every other unique column.
    email: Mapped[str] = mapped_column(unique=True)
    full_name: Mapped[str | None] = mapped_column()
    role: Mapped[str] = mapped_column(default=UserRole.STUDENT.value)
    # Per-user UI/content language. Drives both the i18n bundle on the
    # frontend and which translated copy of course content gets served.
    # The CHECK constraint in supabase/migrations/...add_profile_preferred_locale
    # restricts this to ('ru', 'en'); keep the schema Literal in sync.
    preferred_locale: Mapped[str] = mapped_column(default="ru")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    avatar_url: Mapped[str | None] = mapped_column()

    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"

    @property
    def role_enum(self) -> UserRole:
        return UserRole(self.role) if isinstance(self.role, str) else self.role
