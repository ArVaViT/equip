import hashlib
import hmac
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import Caller, get_caller_even_if_closed, get_current_user, refuse_if_closed, require_admin
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.audit_log import AuditLog
from app.models.enrollment import Enrollment
from app.models.organization import MembershipRole, MembershipStatus, Organization, OrganizationMember
from app.models.user import User, UserRole
from app.schemas.course import CourseDashboardSummary, EnrollmentSummaryResponse
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.user import PreferredLocaleUpdate, UserResponse
from app.services import auth_admin
from app.services.audit_service import log_action
from app.services.course_service import get_user_courses, reading_progress_by_course
from app.services.memberships import active_memberships, mirror_role
from app.services.my_data_export import export_my_data
from app.services.translation.resolve_for_display import (
    build_localized_course_dashboard_summaries,
    should_apply_course_translation_overlay,
)

logger = logging.getLogger(__name__)

# Derived from the enum rather than repeated: a fifth role added to
# ``UserRole`` and forgotten here would be refused by an allow-list
# nobody remembered was a second copy.
VALID_ROLES = tuple(role.value for role in UserRole)

router = APIRouter(prefix="/users", tags=["users"])


def _parse_user_uuid(user_id: str) -> UUID:
    """Parse a path-parameter user id or raise 404.

    Invalid UUIDs are indistinguishable from missing users at the API
    surface, so we normalise both to "User not found".
    """
    try:
        return UUID(user_id)
    except ValueError:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            context={"resource_type": "user", "resource_id": user_id},
        ) from None


def _get_user_or_404(db: Session, uid: UUID) -> User:
    """Fetch a user row or raise the canonical 404.

    Consolidates the fetch-or-404 boilerplate the admin routes repeated.
    The error envelope (code / status / message / context) is
    byte-identical to the hand-written call sites it replaced, so the
    HTTP contract is unchanged.
    """
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            context={"resource_type": "user", "resource_id": str(uid)},
        )
    return user


@router.get("/me/export", summary="Everything Equip keeps about the caller, as a JSON file")
def export_my_data_file(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """The caller's own data, to keep or take elsewhere — see ``services/my_data_export.py``.

    A download, never cached: it carries the person's answers and marks.
    """
    data = export_my_data(db, current_user)
    day = datetime.now(UTC).date().isoformat()
    return JSONResponse(
        data,
        headers={
            "Content-Disposition": f'attachment; filename="equip-my-data-{day}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/me/courses", response_model=list[EnrollmentSummaryResponse])
def get_my_courses(
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EnrollmentSummaryResponse]:
    # Dashboard view: slim payload — only course scalars (no module/chapter
    # tree). ``get_user_courses`` loads courses WITHOUT the tree, so all text
    # hydration here is course-only (``hydrate_modules=False``) to avoid an
    # N+1 lazy-load over modules the dashboard never renders.
    response.headers["Vary"] = "Accept-Language"
    display_locale: LocaleCode = normalize_locale(accept_language)
    rows = get_user_courses(db, current_user.id, skip=skip, limit=limit)
    if not rows:
        return []
    # Reading counts for every course on the page in one grouped query. The
    # percentage beside them is assessment-only, so without this the
    # dashboard reports 0% to somebody who has read the whole course.
    reading = reading_progress_by_course(db, current_user.id, [e.course_id for e in rows])

    def with_reading(enrollment: Enrollment) -> EnrollmentSummaryResponse:
        read, to_read = reading.get(str(enrollment.course_id), (0, 0))
        base = EnrollmentSummaryResponse.model_validate(enrollment, from_attributes=True)
        return base.model_copy(update={"chapters_read": read, "chapters_to_read": to_read})

    courses = [e.course for e in rows if e.course is not None]
    if not courses:
        return [with_reading(e) for e in rows]
    # One bulk content_versions read resolves every course's title/description
    # at the display locale AND hydrates ``course.title`` on the ORM objects, so
    # the owner / admin non-overlay path below (which serialises the course
    # directly via ``CourseDashboardSummary.model_validate``) reads the same
    # resolved text. The old ``populate_spine_texts`` pre-pass here was fully
    # overwritten by this builder — a wasted second cv fetch per request.
    localized = {
        c.id: s
        for c, s in zip(
            courses,
            build_localized_course_dashboard_summaries(db, courses, display_locale),
            strict=True,
        )
    }
    out: list[EnrollmentSummaryResponse] = []
    for e in rows:
        if e.course is None:
            out.append(with_reading(e))
            continue
        c = e.course
        summary = (
            localized[c.id]
            if should_apply_course_translation_overlay(course=c, current_user=current_user)
            else CourseDashboardSummary.model_validate(c, from_attributes=True)
        )
        out.append(with_reading(e).model_copy(update={"course": summary}))
    return out


@router.patch("/me/preferences", response_model=UserResponse)
def update_my_preferences(
    body: PreferredLocaleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Persist the user's preferred locale.

    The frontend hits this whenever the language switcher changes so the
    choice survives across devices. We audit-log the change because role-
    elevated users (teachers/admins) flipping languages can affect what they
    see in the editor and we want a paper trail for support tickets.
    """
    # A guess never overrules a decision. The client reports the browser's
    # language for accounts whose locale nobody ever set — a Google
    # sign-up, where no language reaches ``handle_new_user`` at all — and
    # that report must not touch the locale of somebody who has since
    # picked one. Refused silently: the client is not doing anything
    # wrong, it simply has less information than the profile does.
    if body.detected and current_user.locale_source == "chosen":
        return current_user

    new_source = "detected" if body.detected else "chosen"
    if current_user.preferred_locale == body.preferred_locale:
        # Same language, but possibly a stronger claim to it: confirming a
        # detected value in the first-run screen is a person choosing it,
        # and a 'default' row is upgraded by any signal at all. No audit
        # entry — nothing a reader of the log would care about changed.
        upgrade = not body.detected or current_user.locale_source == "default"
        if upgrade and current_user.locale_source != new_source:
            current_user.locale_source = new_source
            db.commit()
            db.refresh(current_user)
        return current_user

    previous = current_user.preferred_locale
    current_user.preferred_locale = body.preferred_locale
    current_user.locale_source = new_source

    # ``log_action`` COMMITS the session itself (its trailing commit is
    # load-bearing — see audit_service.py). Calling it here, after the
    # locale mutation, makes the locale change and the audit row durable
    # in the SAME commit — both visible or both rolled back. The explicit
    # ``db.commit()`` below is then a no-op kept for readability; do NOT
    # reorder this call after other uncommitted writes you don't want
    # committed along with it.
    log_action(
        db,
        current_user.id,
        "update",
        "user_preferences",
        str(current_user.id),
        details={"preferred_locale": {"from": previous, "to": body.preferred_locale}},
    )

    db.commit()
    db.refresh(current_user)

    return current_user


@router.post("/me/onboarding/complete", response_model=UserResponse)
def complete_my_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Record that this person has been through the first-run flow.

    Idempotent: the timestamp is written once and never moved, so a second
    browser reporting the same thing later does not make the record say the
    flow was finished more recently than it was. No body — there is nothing
    to say beyond "done", and the server's clock is the one that counts.

    Not audited. The audit log is for changes somebody may later need to
    explain; "closed the welcome wizard" is not one of them.
    """
    if current_user.onboarding_completed_at is None:
        current_user.onboarding_completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(current_user)
    return current_user


def _organizations_left_without_a_director(db: Session, user: User) -> list[Organization]:
    """Organizations ``user`` directs where nobody else active does.

    Deleting such an account would leave a school whose cohorts, invitations
    and certificates nobody may run. A teacher's courses do not have this
    problem — they stay with the school, and its director can still manage
    them — so only directing is checked.
    """
    directed = [m.organization_id for m in active_memberships(db, user.id) if m.role == MembershipRole.DIRECTOR.value]
    if not directed:
        return []
    others = {
        organization_id
        for (organization_id,) in db.query(OrganizationMember.organization_id)
        .join(User, User.id == OrganizationMember.user_id)
        .filter(
            OrganizationMember.organization_id.in_(directed),
            OrganizationMember.user_id != user.id,
            OrganizationMember.role == MembershipRole.DIRECTOR.value,
            OrganizationMember.status == MembershipStatus.ACTIVE.value,
            User.deactivated_at.is_(None),
        )
        .all()
    }
    alone = [organization_id for organization_id in directed if organization_id not in others]
    if not alone:
        return []
    return db.query(Organization).filter(Organization.id.in_(alone)).order_by(Organization.public_name).all()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, summary="Delete the caller's own account")
def delete_my_account(
    caller: Caller = Depends(get_caller_even_if_closed),
    db: Session = Depends(get_db),
) -> Response:
    """The delete button on the profile page.

    A soft deletion, the one the admin route has always made, plus the
    owner's mark (``profiles.deleted_at``):

    * ``deactivated_at`` is set, so every guard that already reads it
      applies — the API answers 403, course mail and reminders skip the
      account, rosters and the calendar feed leave it out;
    * other people see «Deleted user» with no email or photo
      (``app.services.deleted_person``);
    * nothing is removed. Marks, submissions, certificates, enrolments and
      courses stay with the school, as the privacy policy says;
    * every session ends (``auth_admin.sign_out_everywhere``).

    The owner can come back through a link emailed to the address
    (``restore_my_account``).

    Twice is not an error: a second request — a double click, a second tab
    — finds the account already deleted and answers 204 again. An account an
    administrator switched off cannot be "deleted" over the top of that; it
    answers what every other route answers it.

    Refused for platform staff, as the admin route refuses an admin deleting
    themselves, and for the only director of an organization.
    """
    user = caller.user
    if user.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    refuse_if_closed(user)

    if user.role == UserRole.ADMIN.value:
        raise equip_error(
            ErrorCode.ACCOUNT_CANNOT_DELETE,
            status_code=status.HTTP_409_CONFLICT,
            message="Platform staff cannot delete their own account; another administrator can.",
            context={"reason": "platform_staff"},
        )
    alone = _organizations_left_without_a_director(db, user)
    if alone:
        raise equip_error(
            ErrorCode.ACCOUNT_CANNOT_DELETE,
            status_code=status.HTTP_409_CONFLICT,
            message="You are the only director of an organization. Appoint another director first.",
            context={
                "reason": "only_director",
                "organizations": [o.public_name for o in alone],
            },
        )

    now = datetime.now(UTC)
    user.deleted_at = now
    user.deactivated_at = now
    # No address in the record, only its fingerprint: the restore checks
    # that the address its link went to is still this one.
    log_action(
        db,
        user.id,
        "delete",
        "user",
        str(user.id),
        details={"mode": "self", "role": user.role, "address_sha256": address_fingerprint(user.email)},
    )
    db.commit()

    if not auth_admin.sign_out_everywhere(caller.token):
        # The account is closed either way — the API refuses every token —
        # and a restore needs an email link opened after this moment.
        logger.warning("account %s deleted, but Supabase did not confirm ending its sessions", user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


#: The ``amr`` methods that mean "opened something we emailed to the
#: account's address": the sign-in link (``magiclink``), the code in the same
#: email (``otp``) and the password-reset link (``recovery``). A password,
#: Google (``oauth``) or a refreshed token is not on the list. GoTrue names
#: the method after the email that was verified (``ParseAuthenticationMethod``).
#: An address-change confirmation also arrives as ``otp`` (``verifyPost``
#: names every token-hash verification so), which is why the restore also
#: refuses an account whose address is not the one it was deleted with
#: (``_still_the_owners_address``). Production Auth should also keep "Secure
#: email change" on and the phone provider off.
EMAIL_PROOF_METHODS = frozenset({"magiclink", "otp", "recovery"})


def _email_proven_at(claims: dict[str, object]) -> datetime | None:
    """When the person behind this token last opened an email we sent them.

    Supabase writes ``amr`` — the methods used and *when* — into every
    access token and carries it unchanged through refreshes, which is the
    point: ``iat`` moves every hour, the moment of sign-in does not.
    """
    amr = claims.get("amr")
    if not isinstance(amr, list):
        return None
    stamps = [
        entry["timestamp"]
        for entry in amr
        if isinstance(entry, dict)
        and entry.get("method") in EMAIL_PROOF_METHODS
        and isinstance(entry.get("timestamp"), int | float)
    ]
    if not stamps:
        return None
    return datetime.fromtimestamp(max(stamps), UTC)


@router.post("/me/restore", status_code=status.HTTP_204_NO_CONTENT, summary="Restore an account its owner deleted")
def restore_my_account(
    caller: Caller = Depends(get_caller_even_if_closed),
    db: Session = Depends(get_db),
) -> Response:
    """Undo ``delete_my_account`` — for the owner, by a link sent to the address.

    Signing in with a password or Google reaches the restore screen; the
    restore itself needs a sign-in through an email we sent to the account's
    address after the deletion (``EMAIL_PROOF_METHODS``). The address is
    what the account belongs to: a password may be shared or guessed, and a
    session that was already open — the laptop at church nobody closed, a
    token refreshed before Supabase revoked it — proves nothing about who
    holds it now. Anything else is refused with
    ``account.restore_needs_email_link``, and the client sends the link.

    This is also how somebody who deleted their account and later "signs up
    again" with the same address gets it back. Supabase never creates a
    second account for an address it holds; the sign-in reaches the old one,
    the API answers ``account.deleted``, and the client offers this. Nothing
    here tells a stranger whether an address was ever registered: only a
    person who has just signed in reaches the question, and only the owner
    of the address can answer it.

    Only the owner's deletion can be undone here. An account an
    administrator switched off answers ``account.deactivated`` as before.
    """
    user = caller.user
    if user.deleted_at is None:
        refuse_if_closed(user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    proven_at = _email_proven_at(caller.claims)
    if proven_at is None or proven_at <= _aware(user.deleted_at):
        raise equip_error(
            ErrorCode.ACCOUNT_RESTORE_NEEDS_EMAIL_LINK,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Open the link we email to this account's address to restore it",
        )

    # The link proves the address it went to — which proves the owner only
    # while that is still the address the account was deleted with. Moving
    # it is the one thing a holder of the password alone could do to an
    # account we closed (review, 2026-10-17); a phone on the account would
    # also sign in as "otp".
    if not _still_the_owners_address(db, user):
        logger.warning("restore of %s refused: the address is not the one it was deleted with", user.id)
        raise equip_error(
            ErrorCode.ACCOUNT_RESTORE_REFUSED,
            status_code=status.HTTP_403_FORBIDDEN,
            message="This account's address changed after it was deleted; write to support to restore it",
        )

    deleted_at = user.deleted_at
    user.deleted_at = None
    user.deactivated_at = None
    log_action(
        db,
        user.id,
        "restore",
        "user",
        str(user.id),
        details={"mode": "self", "deleted_at": _aware(deleted_at).isoformat()},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def address_fingerprint(email: str) -> str:
    """The address, reduced to what a comparison needs."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _still_the_owners_address(db: Session, user: User) -> bool:
    """Whether Supabase still mails this account where it did at the deletion."""
    deletion = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.action == "delete",
            AuditLog.resource_type == "user",
            AuditLog.resource_id == str(user.id),
        )
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    snapshot = (deletion.details or {}).get("address_sha256") if deletion is not None else None
    if not isinstance(snapshot, str):
        # No fingerprint, no proof: an administrator can still restore.
        return False
    now = auth_admin.address_state(user.id)
    return not now.has_phone and hmac.compare_digest(address_fingerprint(now.email), snapshot)


def _aware(moment: datetime) -> datetime:
    """SQLite hands back naive datetimes; Postgres does not. Both are UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class AdminUserMembership(BaseModel):
    """One organization a person is in, as the admin's user list shows it."""

    organization_id: str
    organization_slug: str
    organization_name: str
    role: str
    status: str


class AdminUserRow(BaseModel):
    id: str
    email: str
    full_name: str | None
    #: The platform-wide role — ``admin``, or the mirror of the highest
    #: membership role. *Where* the person holds it is ``memberships``.
    role: str
    avatar_url: str | None
    created_at: datetime | None
    # Non-null when the account is soft-deleted; the admin panel surfaces this
    # so a deactivated user can be told apart and restored.
    deactivated_at: datetime | None
    #: Non-null when the owner deleted the account themselves — always with
    #: ``deactivated_at``. Restoring clears both.
    deleted_at: datetime | None = None
    memberships: list[AdminUserMembership] = []


@router.get("/admin/users", response_model=list[AdminUserRow])
def list_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminUserRow]:
    users = db.query(User).order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    # One grouped query for the page's memberships rather than one per row.
    memberships: dict[UUID, list[AdminUserMembership]] = {}
    if users:
        rows = (
            db.query(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .filter(OrganizationMember.user_id.in_([u.id for u in users]))
            .order_by(Organization.public_name)
            .all()
        )
        for membership, organization in rows:
            memberships.setdefault(membership.user_id, []).append(
                AdminUserMembership(
                    organization_id=str(organization.id),
                    organization_slug=organization.slug,
                    organization_name=organization.public_name,
                    role=membership.role,
                    status=membership.status,
                )
            )
    return [
        AdminUserRow(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            avatar_url=u.avatar_url,
            created_at=u.created_at,
            deactivated_at=u.deactivated_at,
            deleted_at=u.deleted_at,
            memberships=memberships.get(u.id, []),
        )
        for u in users
    ]


class BulkRoleUpdate(BaseModel):
    user_ids: list[str]
    role: str


@router.put("/admin/users/bulk-role")
def bulk_update_user_roles(
    body: BulkRoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if body.role not in VALID_ROLES:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid role",
            context={"resource_type": "user", "role": body.role, "valid_roles": list(VALID_ROLES)},
        )
    if len(body.user_ids) > 100:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Maximum 100 users per batch",
            context={"resource_type": "user", "submitted": len(body.user_ids), "max": 100},
        )

    valid_uuids: list[UUID] = []
    for uid_str in body.user_ids:
        try:
            valid_uuids.append(UUID(uid_str))
        except ValueError:
            continue

    if not valid_uuids:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="No valid user IDs provided",
            context={"resource_type": "user"},
        )

    # Admins must not demote themselves; silently skip their own id.
    safe_uuids = [u for u in valid_uuids if u != admin.id]

    # The same contract as the single route: in or out of ``admin``. A
    # person whose memberships say otherwise is left alone and named in
    # ``held_by_membership`` rather than failing the whole batch — the
    # others asked for are not wrong because one of them was.
    updated = 0
    held: list[str] = []
    for user in db.query(User).filter(User.id.in_(safe_uuids)).all():
        outcome = _move_platform_role(db, user, body.role)
        if outcome == "held":
            held.append(str(user.id))
        elif outcome == "changed":
            updated += 1
    db.commit()

    log_action(
        db,
        admin.id,
        "bulk_role_update",
        "user",
        ",".join(str(u) for u in safe_uuids[:10]),
        details={"new_role": body.role, "count": updated, "held_by_membership": len(held)},
    )

    return {"updated": updated, "role": body.role, "held_by_membership": held}


def _move_platform_role(db: Session, user: User, requested: str) -> str:
    """Move ``user`` in or out of ``admin``; anything else is the mirror's.

    ``profiles.role`` below ``admin`` is a mirror of the person's highest
    organization membership (``mirror_role``, and the trigger in Postgres).
    Writing ``teacher`` or ``director`` here used to hold until the next
    membership write anywhere, which put the old value back: the review's
    probe demoted a director to student and watched a student invitation to
    another school make them a director again. So:

    * ``admin`` makes the person platform staff;
    * any other value asked of an admin stops them being platform staff, and
      the memberships say what is left — ``teacher`` for an admin who also
      teaches somewhere, ``student`` for one who belongs nowhere;
    * any other value asked of a non-admin is accepted only when it is what
      the memberships already say (the mirror is re-run first, so a stale
      profile is repaired by the ask). Otherwise ``"held"``: the role is held
      by a membership and changes there.

    Returns ``"changed"``, ``"unchanged"`` or ``"held"``. Flushes, does not
    commit; nothing is written for ``"held"``.
    """
    before = user.role
    if requested == UserRole.ADMIN.value:
        user.role = UserRole.ADMIN.value
    elif user.role == UserRole.ADMIN.value:
        user.role = UserRole.STUDENT.value
        mirror_role(db, user)
    else:
        mirror_role(db, user)
        if user.role != requested:
            return "held"
    db.flush()
    return "changed" if user.role != before else "unchanged"


@router.put("/admin/users/{user_id}/role")
def update_user_role(
    user_id: str,
    # Validated against ``VALID_ROLES`` below; cap keeps Pydantic from
    # parsing a multi-MB role string before that allow-list check runs.
    role: str = Query(..., max_length=32),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if role not in VALID_ROLES:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid role",
            context={"resource_type": "user", "role": role, "valid_roles": list(VALID_ROLES)},
        )
    uid = _parse_user_uuid(user_id)
    if uid == admin.id:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Cannot change your own role",
            context={"resource_type": "user", "user_id": str(uid)},
        )
    user = _get_user_or_404(db, uid)
    old_role = user.role
    if _move_platform_role(db, user, role) == "held":
        raise equip_error(
            ErrorCode.USER_ROLE_HELD_BY_MEMBERSHIP,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message=(
                "This role is held by the person's organization memberships and changes there; "
                "this route only makes somebody platform staff, or stops them being it"
            ),
            context={
                "resource_type": "user",
                "user_id": str(user.id),
                "requested": role,
                "role": user.role,
                "memberships": [
                    {"organization_id": str(m.organization_id), "role": m.role} for m in active_memberships(db, uid)
                ],
            },
        )
    db.commit()
    db.refresh(user)
    log_action(
        db,
        admin.id,
        "update",
        "user",
        user_id,
        details={"old_role": old_role, "new_role": user.role, "requested": role},
    )
    return {"id": str(user.id), "email": user.email, "role": user.role}


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Soft-delete (deactivate) another user.

    Sets ``deactivated_at`` and blocks the account's login, but PRESERVES every
    owned row (courses, grades, certificates) so the account can be restored
    via ``POST /admin/users/{id}/restore``. This is deliberately reversible —
    it avoids the old half-state where data was hard-deleted while the auth
    identity lingered and resurrected an empty profile on next login.

    An admin cannot delete themselves via this route — that would leave the
    platform without an admin in the worst case. If the last admin truly wants
    to leave, a direct SQL operation through Supabase is the right escape hatch.
    """
    uid = _parse_user_uuid(user_id)
    if uid == admin.id:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Admins cannot delete their own account",
            context={"resource_type": "user", "user_id": str(uid)},
        )

    target = _get_user_or_404(db, uid)

    if target.deactivated_at is not None:
        # Already deactivated — idempotent success.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        log_action(
            db,
            admin.id,
            "delete",
            "user",
            str(uid),
            details={"email": target.email, "role": target.role, "mode": "soft_delete"},
        )
        target.deactivated_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Admin-initiated deactivation failed for user %s", uid)
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="User deletion failed. Please try again or contact support.",
            context={"resource_type": "user", "user_id": str(uid)},
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/users/{user_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def admin_restore_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Reactivate a soft-deleted account (clears ``deactivated_at``).

    The user's data was preserved on deactivation, so restoring re-enables
    login and returns the account exactly as it was. An account its owner
    deleted (``deleted_at``) is restored the same way — both columns are
    cleared, and the name is shown to others again. Supabase was never told
    to ban the account, so there is nothing there to undo.
    """
    uid = _parse_user_uuid(user_id)

    target = _get_user_or_404(db, uid)

    if target.deactivated_at is None:
        # Already active — idempotent success.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    log_action(
        db,
        admin.id,
        "restore",
        "user",
        str(uid),
        details={"email": target.email, "role": target.role, "self_deleted": target.deleted_at is not None},
    )

    target.deactivated_at = None
    target.deleted_at = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
