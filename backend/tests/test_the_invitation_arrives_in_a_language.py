"""An invitation is the first thing anyone receives from this platform.

It went out in English to everyone, whatever school sent it. A German
teacher being asked to join a Bible school had to read English to find
out what they were being asked — on a platform whose whole point is that
people learn in their own language.

There is no preference to read: the person being invited has no account
yet. The next best answer is the language of whoever is inviting. An
admin writing to their own community almost always shares its language,
and it beats defaulting the world to English.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.user import User
from app.services.email_service import _invitation_html
from app.services.invitation_service import _inviter_locale

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _make_admin(db: Session, locale: str | None) -> uuid.UUID:
    admin_id = uuid.uuid4()
    db.add(
        User(
            id=admin_id,
            email=f"{admin_id}@example.com",
            role="admin",
            preferred_locale=locale,
        )
    )
    db.commit()
    return admin_id


class TestTheLanguageIsChosen:
    @pytest.mark.parametrize("locale", ["ru", "en", "de", "uk"])
    def test_it_follows_the_inviter(self, db: Session, locale: str):
        admin_id = _make_admin(db, locale)
        assert _inviter_locale(db, admin_id) == locale

    def test_an_unknown_inviter_falls_back(self, db: Session):
        # A system-issued invitation with no author behind it still has to
        # go out; it goes out in the platform default.
        assert _inviter_locale(db, None) == "ru"

    def test_an_inviter_with_no_preference_falls_back(self, db: Session):
        admin_id = _make_admin(db, None)
        assert _inviter_locale(db, admin_id) == "ru"


class TestTheEmailReadsInThatLanguage:
    def test_german(self):
        html = _invitation_html("teacher", "https://equipbible.com/invite/x", "de")
        assert "eingeladen" in html
        assert "Einladung annehmen" in html
        assert "Dozent" in html
        # The English copy must be gone, not merely accompanied.
        assert "You've been invited" not in html

    def test_ukrainian(self):
        html = _invitation_html("student", "https://equipbible.com/invite/x", "uk")
        assert "запросили" in html
        assert "Прийняти запрошення" in html
        assert "студент" in html

    def test_russian(self):
        html = _invitation_html("teacher", "https://equipbible.com/invite/x", "ru")
        assert "Принять приглашение" in html
        assert "преподаватель" in html

    def test_english_is_unchanged(self):
        html = _invitation_html("student", "https://equipbible.com/invite/x", "en")
        assert "Accept invitation" in html
        assert "student" in html

    @pytest.mark.parametrize("locale", ["ru", "en", "de", "uk"])
    def test_the_link_survives_every_language(self, locale: str):
        url = "https://equipbible.com/invite/token-123"
        assert url in _invitation_html("teacher", url, locale)

    @pytest.mark.parametrize("locale", ["ru", "en", "de", "uk"])
    def test_an_unknown_role_still_sends(self, locale: str):
        # A role with no catalog entry must not break delivery — the raw
        # value is shown rather than an exception raised.
        html = _invitation_html("observer", "https://equipbible.com/invite/x", locale)
        assert "observer" in html
