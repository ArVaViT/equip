"""An invitation nobody answers is noticed before it expires.

``services/invitation_watch.notice_unanswered``, run hourly by cron. Every
teacher invited in October 2026 expired unseen, and the person who sent the
invitations learned it from a messenger weeks later. Pinned here: the sender
is told once, in the bell, while the link still works; not for an answered,
withdrawn or long-lived invitation; not twice; and again after a resend.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.database import get_db
from app.main import app
from app.models.invitation import Invitation, InvitationScope, InvitationStatus
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.services.invitation_service import create_or_resend_invitation
from app.services.invitation_watch import INVITATIONS_LINK, NOTIFICATION_TYPE, notice_unanswered
from app.services.notification_service import render_notification
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

EMAIL = "slow-to-answer@example.com"
SECRET = "test-worker-secret"


def _invitation(db: Session, *, expires_in: timedelta, **extra: object) -> Invitation:
    invitation = Invitation(
        email=EMAIL,
        role=UserRole.TEACHER.value,
        scope=InvitationScope.ORGANIZATION.value,
        invited_by=ADMIN_ID,
        organization_id=TEST_ORGANIZATION_ID,
        expires_at=datetime.now(UTC) + expires_in,
        **extra,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def _bell(db: Session) -> list[Notification]:
    return db.query(Notification).filter(Notification.user_id == ADMIN_ID).all()


@pytest.mark.usefixtures("admin")
class TestTheSenderIsTold:
    def test_once_while_the_link_still_works(self, db: Session) -> None:
        invitation = _invitation(db, expires_in=timedelta(hours=30))

        assert notice_unanswered(db) == 1
        assert notice_unanswered(db) == 0, "a second sweep must not repeat it"

        [notice] = _bell(db)
        assert notice.type == NOTIFICATION_TYPE
        assert notice.link == INVITATIONS_LINK
        title, message = render_notification(notice, "ru")
        assert title == "Приглашение ещё не принято"
        assert EMAIL in message
        db.refresh(invitation)
        assert invitation.unanswered_noticed_at is not None
        assert invitation.status == InvitationStatus.PENDING.value

    def test_again_after_a_resend_gives_the_link_a_fresh_week(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.services.invitation_service._mail_the_invitation", lambda *a, **k: None)
        invitation = _invitation(db, expires_in=timedelta(hours=30))
        assert notice_unanswered(db) == 1

        create_or_resend_invitation(
            db,
            email=EMAIL,
            role=UserRole.TEACHER.value,
            invited_by=ADMIN_ID,
            organization_id=TEST_ORGANIZATION_ID,
        )
        db.refresh(invitation)
        assert invitation.unanswered_noticed_at is None

        # Five days on, the fresh week is in its last two days.
        assert notice_unanswered(db, now=datetime.now(UTC) + timedelta(days=5, hours=12)) == 1
        assert len(_bell(db)) == 2


@pytest.mark.usefixtures("admin")
class TestNobodyIsTold:
    @pytest.mark.parametrize(
        "expires_in",
        [timedelta(days=5), timedelta(minutes=30), -timedelta(hours=1)],
        ids=["plenty-of-time", "minutes-left", "already-expired"],
    )
    def test_outside_the_window(self, db: Session, expires_in: timedelta) -> None:
        _invitation(db, expires_in=expires_in)

        assert notice_unanswered(db) == 0
        assert _bell(db) == []

    @pytest.mark.parametrize(
        ("status", "extra"),
        [
            (InvitationStatus.ACCEPTED.value, {"accepted_at": datetime.now(UTC)}),
            (InvitationStatus.REVOKED.value, {}),
            (InvitationStatus.FULFILLED.value, {"fulfilled_at": datetime.now(UTC)}),
        ],
    )
    def test_about_an_invitation_that_was_answered_or_withdrawn(
        self, db: Session, status: str, extra: dict[str, object]
    ) -> None:
        _invitation(db, expires_in=timedelta(hours=30), status=status, **extra)

        assert notice_unanswered(db) == 0
        assert _bell(db) == []

    def test_when_the_sender_s_account_is_switched_off(self, db: Session, admin: User) -> None:
        admin.deactivated_at = datetime.now(UTC)
        db.commit()
        invitation = _invitation(db, expires_in=timedelta(hours=30))

        assert notice_unanswered(db) == 0
        assert _bell(db) == []
        db.refresh(invitation)
        assert invitation.unanswered_noticed_at is not None, "nobody to tell is not a reason to look again hourly"


class TestTheCron:
    @pytest.fixture()
    def worker(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        monkeypatch.setattr("app.core.config.settings.TRANSLATION_WORKER_SECRET", SecretStr(SECRET), raising=False)

        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        with TestClient(app, raise_server_exceptions=False) as tc:
            yield tc

    @pytest.mark.usefixtures("admin")
    def test_runs_the_sweep_with_the_secret(self, worker: TestClient, db: Session) -> None:
        _invitation(db, expires_in=timedelta(hours=30))

        response = worker.get("/api/v1/internal/invitation-watch", headers={"Authorization": f"Bearer {SECRET}"})

        assert response.status_code == 200, response.text
        assert response.json() == {"noticed": 1}

    def test_refuses_without_it(self, worker: TestClient) -> None:
        assert worker.get("/api/v1/internal/invitation-watch").status_code == 401
