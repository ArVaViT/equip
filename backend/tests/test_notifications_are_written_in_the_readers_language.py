"""A notification arrives in a list of other notifications.

That is what makes an untranslated one so visible: the certificate
notice is in the reader's language, the announcement is in the reader's
language, and between them sits "Assignment Graded — Your submission for
… has been graded: 9/10" in English, for a student who never chose
English.

Three of five kinds went through the catalog. Two were written as
literals at the call site: ``assignment_graded``, which is the most
frequent notification the platform sends, and ``retake_requested``,
which goes to a teacher. Both shipped with the German and Ukrainian
rollout and neither had a test, because the notification tests check
*kinds* rather than words.

The guard here is structural rather than a list of the two: a literal
passed as ``title`` or ``message`` is the mistake, whoever makes it
next. It follows ``test_notification_kinds`` in walking the call sites
with ``ast`` — a hand-written list of localized call sites would drift
exactly the way the kinds list did.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.core.i18n import _CATALOG, t
from app.models.user import User
from app.schemas.locale import LOCALE_CODES
from app.services.user_locale import preferred_locale_of

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

APP = Path(__file__).resolve().parent.parent / "app"
EMITTERS = {"create_notification", "create_notifications_bulk"}
LOCALIZED_ARGS = ("title", "message")


def _call_name(node: ast.Call) -> str:
    return node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")


def _looks_localized(value: ast.expr) -> bool:
    """Whether this argument reaches the catalog.

    A name or attribute is accepted: the call sites that assign
    ``notif_title = t(locale, …)`` first are the pattern this file is
    protecting, not one it should outlaw. What it rejects is text
    written at the call site, where no language was ever chosen.
    """
    if isinstance(value, ast.Constant | ast.JoinedStr):
        return False
    if isinstance(value, ast.Call):
        return _call_name(value) == "t"
    return isinstance(value, ast.Name | ast.Attribute | ast.Subscript | ast.IfExp)


def _literal_notification_texts() -> list[str]:
    offences: list[str] = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in EMITTERS:
                continue
            for keyword in node.keywords:
                if keyword.arg in LOCALIZED_ARGS and not _looks_localized(keyword.value):
                    offences.append(f"{path.relative_to(APP)}:{node.lineno} {keyword.arg}=")
    return offences


def test_no_notification_text_is_written_at_the_call_site():
    offences = _literal_notification_texts()
    assert not offences, "these notifications would reach every reader in one language: " + ", ".join(offences)


class TestTheCatalogCanAnswer:
    @pytest.mark.parametrize("locale", LOCALE_CODES)
    def test_the_new_keys_exist_everywhere(self, locale: str):
        for key in (
            "notif.assignment_graded.title",
            "notif.assignment_graded.body",
            "notif.retake_requested.title",
            "notif.retake_requested.body",
            "fallback.your_assignment",
        ):
            assert key in _CATALOG[locale], f"{locale} is missing {key}"

    def test_the_grade_reads_as_a_grade_in_each_language(self):
        rendered = {
            locale: t(locale, "notif.assignment_graded.body", title="Romans 8", grade="9", max_score="10")
            for locale in LOCALE_CODES
        }
        # Every language says nine out of ten, and no two say it the
        # same way — a catalog entry that was copied rather than
        # translated shows up here.
        assert all("9" in text and "10" in text for text in rendered.values())
        assert len(set(rendered.values())) == len(LOCALE_CODES)


class TestWhoseLanguageItIs:
    def test_it_is_the_reader_who_chose(self, db: Session):
        user_id = uuid.uuid4()
        db.add(User(id=user_id, email=f"{user_id}@example.com", role="student", preferred_locale="uk"))
        db.commit()
        assert preferred_locale_of(db, user_id) == "uk"

    def test_an_account_that_never_said_is_written_to_in_english(self, db: Session):
        # A row with nothing in the column is not evidence that this
        # person reads Russian. It is evidence that nobody asked.
        user_id = uuid.uuid4()
        db.add(User(id=user_id, email=f"{user_id}@example.com", role="student", preferred_locale=None))
        db.commit()
        assert preferred_locale_of(db, user_id) == "en"

    def test_nobody_at_all_still_resolves(self, db: Session):
        # System-issued mail and notifications have no author behind
        # them and still have to go out — in English, the language for a
        # reader we know nothing about.
        assert preferred_locale_of(db, None) == "en"


class TestTheBellFollowsTheReader:
    """A notification used to be finished text, written once in whatever
    language the writer resolved at the time. Switch your language and
    the bell stayed in the old one — for every notification you had
    already received, forever.

    It now carries the recipe as well as the text: the catalog key and
    the values. The list route renders it in the language being asked
    for right now.
    """

    def _notify(self, db: Session, user_id, **kwargs):
        from app.services.notification_service import create_notification, notification_text

        return create_notification(
            db,
            user_id=user_id,
            type="certificate_approved",
            title="Certificate Approved",
            message='Your certificate for "Acts" has been approved!',
            i18n=notification_text("notif.cert_approved", course="Acts"),
            **kwargs,
        )

    def test_the_same_row_reads_in_whichever_language_is_asked_for(self, db: Session):
        from app.services.notification_service import render_notification

        user_id = uuid.uuid4()
        db.add(User(id=user_id, email=f"{user_id}@example.com", role="student", preferred_locale="ru"))
        db.commit()
        row = self._notify(db, user_id)
        db.commit()

        rendered = {locale: render_notification(row, locale) for locale in LOCALE_CODES}

        assert len({title for title, _ in rendered.values()}) == len(LOCALE_CODES)
        assert rendered["de"][0] == t("de", "notif.cert_approved.title")
        assert "Acts" in rendered["uk"][1]

    def test_a_row_written_before_the_recipe_keeps_its_text(self, db: Session):
        from app.services.notification_service import create_notification, render_notification

        user_id = uuid.uuid4()
        db.add(User(id=user_id, email=f"{user_id}@example.com", role="student", preferred_locale="ru"))
        db.commit()
        row = create_notification(
            db,
            user_id=user_id,
            type="certificate_approved",
            title="Certificate Approved",
            message="Your certificate has been approved!",
        )
        db.commit()

        assert render_notification(row, "de") == ("Certificate Approved", "Your certificate has been approved!")

    def test_a_key_that_left_the_catalog_falls_back_rather_than_showing_the_key(self, db: Session):
        from app.services.notification_service import create_notification, notification_text, render_notification

        user_id = uuid.uuid4()
        db.add(User(id=user_id, email=f"{user_id}@example.com", role="student", preferred_locale="ru"))
        db.commit()
        row = create_notification(
            db,
            user_id=user_id,
            type="certificate_approved",
            title="Stored title",
            message="Stored message",
            i18n=notification_text("notif.no_longer_exists"),
        )
        db.commit()

        assert render_notification(row, "de") == ("Stored title", "Stored message")
