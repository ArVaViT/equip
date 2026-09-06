import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.enrollment import Enrollment


class UserRole(enum.StrEnum):
    #: Platform staff. The translation queue, user administration, health,
    #: the audit log — everything that belongs to Equip rather than to any
    #: one organization.
    ADMIN = "admin"
    #: An organization's own administrator: its cohorts, its ведомости, its
    #: invitations, its certificates, its settings. Deliberately not the
    #: same role as ADMIN — see the note on ``chk_profiles_role`` in
    #: ``20260826120000_a_director_is_not_a_platform_admin.sql``.
    DIRECTOR = "director"
    TEACHER = "teacher"
    STUDENT = "student"


#: The roles that author and run courses. A director is an organization's
#: administrator *and* very often the one teaching in it — a school small
#: enough to have one director rarely has a separate faculty — so the
#: teaching surface is open to both. This tuple is the single definition:
#: ``require_teacher`` and the frontend's ``canTeach`` mirror it, and a
#: route must never spell the pair out again by hand. Platform staff pass
#: because they administer every organization's courses by definition.
#:
#: What this does NOT grant: ownership. Whether a director may edit *this*
#: course is still ``created_by`` (see ``assert_course_owner``), exactly
#: as it is for a teacher.
TEACHING_ROLES: frozenset[str] = frozenset({UserRole.ADMIN.value, UserRole.DIRECTOR.value, UserRole.TEACHER.value})


def can_teach(role: str) -> bool:
    """Is this role allowed onto the course-authoring surface?"""
    return role in TEACHING_ROLES


class User(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        # Mirror the prod CHECK constraints so the SQLite test path and the
        # Postgres schema-smoke job enforce the same value domains.
        CheckConstraint("role IN ('admin', 'director', 'teacher', 'student')", name="chk_profiles_role"),
        CheckConstraint("preferred_locale IN ('ru', 'en', 'de', 'uk')", name="profiles_preferred_locale_check"),
        CheckConstraint(
            "locale_source IN ('default', 'detected', 'chosen')",
            name="profiles_locale_source_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # ``unique=True`` already creates a B-tree; a second ``index=True`` would
    # just duplicate writes. Same logic applies to every other unique column.
    email: Mapped[str] = mapped_column(unique=True)
    full_name: Mapped[str | None] = mapped_column()
    #: The organization this person belongs to, in whatever role they
    #: hold there. Nullable because platform staff belong to none — and
    #: that null must never satisfy an organization check by accident,
    #: which is why every comparison is written ``IS NOT NULL AND =``
    #: rather than ``=`` alone.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    role: Mapped[str] = mapped_column(default=UserRole.STUDENT.value)
    # Per-user UI/content language. Drives both the i18n bundle on the
    # frontend and which translated copy of course content gets served.
    # The CHECK constraint in supabase/migrations/...add_profile_preferred_locale
    # restricts this to ('ru', 'en', 'de', 'uk'); keep the schema Literal in sync.
    #
    # The default is what an account gets when its signup carried no
    # language at all (Google OAuth passes none) — a row that means "nobody
    # said", which is exactly what ``locale_source = 'default'`` below
    # records. English, matching ``DEFAULT_LOCALE``; it was 'ru' from the
    # Russian-only days. The DB-side DEFAULT is moved by
    # supabase/migrations/20260820120000_english_is_the_last_resort.sql —
    # this ORM default only applies to rows this application inserts.
    preferred_locale: Mapped[str] = mapped_column(default="en")
    # How ``preferred_locale`` got its value: 'default' (nobody was asked
    # — the column is NOT NULL and had to hold something), 'detected'
    # (the browser's language, good enough to serve), or 'chosen' (a
    # person picked it, and nothing automatic may overwrite it).
    #
    # Without this the column could not tell "Russian" from "we had to
    # write something and Russian was the fallback", so a German who
    # signed in with Google — which carries no locale into
    # ``handle_new_user`` — had the interface switched to Russian the
    # moment their profile loaded. See
    # ``supabase/migrations/20260817131500_a_language_nobody_chose_is_not_a_choice.sql``.
    locale_source: Mapped[str] = mapped_column(default="default", server_default="default")
    # Floor for iCal token ``iat`` claims. When a user rotates their
    # subscription token via ``POST /calendar/ical/token``, we stamp
    # this to the new ``iat``; the feed verifier refuses tokens whose
    # ``iat`` is older. Without this, JWT's default decode does NOT
    # validate ``iat``, so a leaked subscribe URL would stay valid for
    # the full 365-day TTL even after the user "rotated".
    calendar_ical_min_iat: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    avatar_url: Mapped[str | None] = mapped_column()
    # Soft-delete marker. The admin "delete user" action sets this instead of
    # purging data: every owned row is preserved and the login is blocked
    # (see ``get_current_user``) until an admin restores the account (clears
    # this back to NULL). Avoids the old half-state where data was hard-deleted
    # but the auth identity lingered and resurrected an empty profile.
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"

    @property
    def role_enum(self) -> UserRole:
        return UserRole(self.role) if isinstance(self.role, str) else self.role
