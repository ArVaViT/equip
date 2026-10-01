import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.enrollment import Enrollment


# JSONB in Postgres, JSON in the SQLite test database (as in org_settings).
_JSONVariant = JSONB().with_variant(JSON(), "sqlite")


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


#: How much of the product a role opens, least to most. It exists for one
#: question — "would this change take something away?" — and the only
#: caller today is accepting an invitation, which used to write the
#: invited role unconditionally and so turned a director who accepted a
#: student invitation into a student.
#:
#: This is a reach ordering, not a hierarchy of authority: a platform
#: admin is not a "better director", the two answer to different things.
#: Do not use it to decide whether one person may act on another.
_ROLE_RANK: dict[str, int] = {
    UserRole.STUDENT.value: 0,
    UserRole.TEACHER.value: 1,
    UserRole.DIRECTOR.value: 2,
    UserRole.ADMIN.value: 3,
}


def higher_role(current: str, offered: str) -> str:
    """The role a person should end up with when they are offered one.

    An unknown value on either side loses to the known one rather than
    raising: the caller is in the middle of a transaction a person is
    waiting on, and a role nobody recognises should not be able to
    silently outrank one we do.
    """
    return offered if _ROLE_RANK.get(offered, -1) > _ROLE_RANK.get(current, -1) else current


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
        CheckConstraint(
            "time_zone_source IN ('default', 'detected', 'chosen')",
            name="profiles_time_zone_source_check",
        ),
        CheckConstraint(
            "birth_date IS NULL OR birth_date >= '1900-01-01'",
            name="profiles_birth_date_floor_check",
        ),
        # Not mirrored, like ``organizations.slug``: ``profiles_country_code_check``
        # is a regex (SQLite has no ``~``) and ``profiles_personal_text_lengths_check``
        # uses ``char_length`` (SQLite has ``length``). A constraint the test
        # database cannot build is worse than the two places that enforce it:
        # Postgres, and the profile form. The backend never writes these fields.
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
    # The zone this person reads times in — an IANA name such as
    # "America/Indiana/Indianapolis". Every instant is stored and served in
    # UTC; this only decides how it is shown (and how a wall-clock time a
    # teacher types is turned back into an instant). Set from the browser
    # ('detected') until the person picks one ('chosen'); see
    # supabase/migrations/20260930132351_a_profile_knows_where_and_when_you_are.sql,
    # which also validates the name against pg_timezone_names.
    time_zone: Mapped[str | None] = mapped_column()
    time_zone_source: Mapped[str] = mapped_column(default="default", server_default="default")
    # Reserved: a client may not write it until a number can be verified
    # (guarded by trg_profiles_protect_immutable_fields).
    phone: Mapped[str | None] = mapped_column()
    # Optional details a person may give about themselves.
    birth_date: Mapped[date | None] = mapped_column(Date)
    #: ISO 3166-1 alpha-2, upper case.
    country_code: Mapped[str | None] = mapped_column()
    region: Mapped[str | None] = mapped_column()
    city: Mapped[str | None] = mapped_column()
    church: Mapped[str | None] = mapped_column()
    #: Kinds of course mail this person turned off (``app.services.email.
    #: course_mail.KINDS``). Empty — the default — is "everything". Account
    #: mail is never in it: it cannot be turned off. The allowed values are
    #: held by ``profiles_email_off_check`` in Postgres, not mirrored here
    #: (SQLite has no ``jsonb_typeof``).
    email_off: Mapped[list[str]] = mapped_column(_JSONVariant, default=list, server_default="[]")
    #: A teacher's saved feedback comments, written by them from the grading
    #: screens and read by nothing on the server. At most fifty
    #: (``profiles_comment_library_check``, not mirrored for the same reason).
    comment_library: Mapped[list[str]] = mapped_column(_JSONVariant, default=list, server_default="[]")
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
    # When this person finished the first-run flow — picked a course, opened
    # the catalogue instead, or said "maybe later". NULL means they have not,
    # and the flow shows again. Until 2026-09 this lived only in the
    # browser's ``localStorage``, so a second device, a private window or
    # cleared site data asked a returning student to set up their account
    # and choose a course all over again. Consent is NOT recorded here — it
    # has its own table (``legal_acceptances``) because it is evidence, and
    # this is a preference.
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"

    @property
    def role_enum(self) -> UserRole:
        return UserRole(self.role) if isinstance(self.role, str) else self.role
