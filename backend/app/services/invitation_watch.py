"""An invitation nobody answers is noticed before it expires.

An invitation lives seven days and used to end in silence. The person who
sent it learned nothing unless they opened the list and read the badge, and
by then the link was dead: every teacher invited in October 2026 expired
that way, two of them after signing up on their own and never coming back.

So the sender is told, in the bell, while the link still works, that nobody
has answered it — early enough to reach the person another way (most of
these invitations follow a conversation in a messenger) or to send it again.
Signing in under the invited address accepts it too (``claim_invitations``),
so "sign in to Equip" is now a complete thing to tell somebody.

Run hourly by Vercel Cron. Each invitation is noticed once per week of life:
the stamp (``invitations.unanswered_noticed_at``) is written before the
notification, so a crash costs one notice and never repeats one, and a
resend clears it along with giving the link a fresh week.

Bell only, like the hour-before reminder: it asks nothing of the reader's
mailbox, and the person who sends invitations is in the app.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.core.i18n import t
from app.core.metrics import emit
from app.models.invitation import Invitation, InvitationStatus
from app.models.user import User
from app.services.notification_service import create_notification, notification_text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: How long before the expiry the sender is told.
NOTICE_WITHIN = timedelta(hours=48)

#: Too close to the end to be worth saying "soon": with the cron down for a
#: day, a notice arriving minutes before the link dies is only noise.
TOO_LATE = timedelta(hours=1)

#: Where the sender reads and resends their invitations — the same tab for
#: platform staff and for a school's director.
INVITATIONS_LINK = "/admin?tab=invitations"

NOTIFICATION_TYPE = "invitation_unanswered"


def notice_unanswered(db: Session, *, now: datetime | None = None) -> int:
    """Tell each sender about their invitations close to expiry; return how many."""
    now = now or datetime.now(UTC)
    due = (
        db.query(Invitation)
        .filter(
            Invitation.status == InvitationStatus.PENDING.value,
            Invitation.unanswered_noticed_at.is_(None),
            Invitation.invited_by.is_not(None),
            Invitation.expires_at > now + TOO_LATE,
            Invitation.expires_at <= now + NOTICE_WITHIN,
        )
        .order_by(Invitation.expires_at)
        .all()
    )
    noticed = 0
    for invitation in due:
        invitation.unanswered_noticed_at = now
        sender = db.get(User, invitation.invited_by)
        # Nobody to tell: the account is gone or switched off.
        if sender is None or sender.deleted_at is not None or sender.deactivated_at is not None:
            continue
        recipe = notification_text("notif.invitation_unanswered", email=invitation.email)
        create_notification(
            db,
            sender.id,
            type=NOTIFICATION_TYPE,
            # The stored fallback, in English, for a row the catalog can no
            # longer render; the recipe is what a reader normally sees.
            title=t("en", "notif.invitation_unanswered.title"),
            message=t("en", "notif.invitation_unanswered.body", email=invitation.email),
            link=INVITATIONS_LINK,
            metadata={"invitation_id": str(invitation.id)},
            i18n=recipe,
        )
        noticed += 1
    db.commit()
    if due:
        emit("equip.invitations.unanswered_noticed_total", float(noticed))
        logger.info("invitation_watch.noticed", extra={"invitations": len(due), "notified": noticed})
    return noticed
