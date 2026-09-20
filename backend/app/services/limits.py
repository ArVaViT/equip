"""What one account may hold, in one place, so the number can move.

Equip runs on a managed Postgres with a finite disk, and the rows a
teacher creates are not free: a course is a handful of bytes, but the
tree under it — modules, chapters, blocks — is multiplied by four in
``content_versions``, because every authored string is stored once per
supported locale. Production today is 47 MB, of which ``content_versions``
alone is 24 MB. So there is a ceiling somewhere, and the platform should
meet it as a rule it chose rather than as a disk that filled up.

This module is that rule. It is deliberately small and deliberately
*indirect*:

* ``LimitKey`` names a thing that can be capped. One member today.
* ``BASE_PLAN`` is the package every account gets. It is a dict, not a
  constant sprinkled through the routes, because the next thing that
  happens to it is that it stops being the only one — a paid tier, a
  verified-organization tier, a per-school exception granted by hand.
  When that day comes, ``plan_for`` starts returning something other
  than ``BASE_PLAN`` and nothing else in the codebase changes.
* ``limit_for`` is the only function a caller asks. It resolves the
  number through the layers that may override it, most specific first.

What this module is NOT: a billing system, a subscription model, or a
table. There is no tier to store yet, and a schema invented before its
first real customer is a migration written twice.

Exemptions: platform admins. They seed content, migrate a school's back
catalogue and clean up after both, and a cap that stops that work is a
cap that gets raised to infinity within the week — at which point it
protects nothing for anybody.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from fastapi import status
from sqlalchemy import func

from app.core.config import settings
from app.core.errors import ErrorCode, equip_error
from app.models.course import Course
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class LimitKey(enum.StrEnum):
    """A thing an account may only hold so much of."""

    COURSES_PER_TEACHER = "courses_per_teacher"
    """Live (non-deleted) courses a single teacher owns. Counted by
    ``courses.created_by``, so a teacher who trashes a course frees the
    slot and one who is merely *taught alongside* consumes none."""


#: ``None`` as a limit means "no ceiling" — the spelling a future
#: unlimited tier will use, so callers already handle it.
Unlimited = None

#: The package every account gets today. One entry; adding the second is
#: a line here plus a call to ``assert_within_limit`` at the write path
#: that creates the row.
BASE_PLAN: dict[LimitKey, int | None] = {
    # Five is a working teacher's shape, not a cliff: a Bible-school
    # teacher carries a few subjects at a time, and the cases that
    # justified a cap at all — a runaway script, a misread UI clicking
    # "create" forty times — are nowhere near it. Someone who genuinely
    # needs a sixth is a conversation, and the conversation now has a
    # dial to turn instead of a deploy to wait for.
    LimitKey.COURSES_PER_TEACHER: 5,
}

#: Deployment-level overrides, read from the environment. A self-hosted
#: Equip may run a different shape of school than equipbible.com does,
#: and a test wants to reach a limit in two rows rather than five.
_DEPLOYMENT_OVERRIDES: dict[LimitKey, str] = {
    LimitKey.COURSES_PER_TEACHER: "MAX_COURSES_PER_TEACHER",
}


def is_exempt(user: User) -> bool:
    """Platform admins are not metered. See the module docstring."""
    return user.role == UserRole.ADMIN.value


def plan_for(user: User) -> dict[LimitKey, int | None]:
    """The plan this account is on.

    Everybody is on the base plan. The signature takes the user because
    the day a second plan exists, this is the function that learns about
    it — and every call site already passes what it will need.
    """
    del user  # one plan today; see the module docstring
    return BASE_PLAN


def limit_for(user: User, key: LimitKey) -> int | None:
    """How many of ``key`` this account may hold, or ``None`` for no cap.

    Resolved most-specific-first: a deployment override beats the plan.
    An organization-level override slots in between the two when there
    is somewhere to store one.
    """
    env_name = _DEPLOYMENT_OVERRIDES.get(key)
    if env_name is not None:
        override = getattr(settings, env_name, None)
        if override is not None:
            return int(override)
    return plan_for(user)[key]


def assert_within_limit(user: User, key: LimitKey, *, current: int) -> None:
    """Raise ``PLAN_LIMIT_REACHED`` (409) if one more would be too many.

    ``current`` is the caller's own count — the write paths already know
    how to count their rows under whatever lock they hold, and a helper
    that counted for them would either duplicate that query or race it.
    """
    if is_exempt(user):
        return
    limit = limit_for(user, key)
    if limit is None or current < limit:
        return
    raise equip_error(
        ErrorCode.PLAN_LIMIT_REACHED,
        status_code=status.HTTP_409_CONFLICT,
        message=f"This account may hold {limit} of these ({key.value}); it holds {current}.",
        context={"limit_key": key.value, "limit": limit, "current": current},
    )


def live_course_count(db: Session, teacher_id: object) -> int:
    """Live courses owned by ``teacher_id``.

    Soft-deleted courses do not count: trashing a course must free its
    slot, or "delete and start over" dead-ends a legitimate teacher.
    """
    return (
        db.query(func.count(Course.id)).filter(Course.created_by == teacher_id, Course.deleted_at.is_(None)).scalar()
        or 0
    )


def assert_can_own_another_course(db: Session, teacher: User) -> None:
    """The course-count gate, for every path that hands a teacher a new
    course row: create, clone, and restore-from-trash alike.

    Restore is included on purpose. It turns a tombstoned tree back into
    live rows, which is the same cost to the database as creating one —
    and a gate that ignored it would let a teacher park courses in the
    trash and pull them back out past the cap.
    """
    if is_exempt(teacher):
        return
    assert_within_limit(
        teacher,
        LimitKey.COURSES_PER_TEACHER,
        current=live_course_count(db, teacher.id),
    )
