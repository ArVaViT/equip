"""How a person who deleted their account is shown to everybody else.

An account its owner deleted (``profiles.deleted_at``) stays in the
database: the school's records of it — marks, submissions, certificates,
enrolments — are the school's, and a roster with a hole in it is worse than
one with a gap labelled. What goes is the *person*: wherever the API shows one
human being to another, a deleted account is «Deleted user», with no email
address and no photo.

Most lists never meet one. Gradebooks, the grading queue, analytics, the
students-at-risk list, cohort rosters and an organization's directors all
leave a deactivated account out altogether — they filter on
``deactivated_at``, and a deleted account is always deactivated (the
``profiles_deleted_is_deactivated_check`` constraint). This module is for the
places that show a person *regardless*: a course's author tab, the
certificate queue and the public verification page's fallback, one
student's grade looked up by id, the history of who changed a mark. Each of
them asks here rather than checking ``deleted_at`` itself:

* ``shown_name`` / ``shown_email`` / ``shown_avatar`` — for a row that has
  the column and ``deleted_at`` beside it;
* ``label`` — the words, in the language of the request.

What is deliberately **not** masked:

* the person themselves (they cannot see anything anyway: every route
  answers 403 ``account.deleted``);
* platform staff in ``/users/admin/*`` — the admin list has to show who
  this is, or nobody could restore it;
* names already frozen into an issued certificate or grade sheet. Those are
  documents the school issued, the policy says they outlive the account, and
  the public verification page exists to show the name a certificate was
  issued to. A certificate that changed its holder's name to «Deleted user»
  the day they closed their account would be worth nothing to them. The
  same goes for the teacher of record frozen into a letterhead at closing
  (``grade_sheet_service._letterhead``, ``certificate_service._snapshot_letterhead``).

An account an administrator switched off (``deactivated_at`` without
``deleted_at``) keeps its name. That is a suspension, decided by somebody
else and reversible by them; the person did not ask to disappear.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

from app.schemas.locale import DEFAULT_LOCALE, normalize_locale

if TYPE_CHECKING:
    from datetime import datetime

#: «Deleted user», in every language the interface speaks. Printed by the
#: API rather than by the web app because the name arrives ready to print, in
#: a dozen response shapes that would otherwise each need a flag.
LABELS: dict[str, str] = {
    "en": "Deleted user",
    "ru": "Удалённый пользователь",
    "de": "Gelöschter Nutzer",
    "uk": "Видалений користувач",
}

#: The language of the request being served, set from ``Accept-Language`` by
#: the request middleware (``app.main``). The web app sends its interface
#: language on every call, so a teacher reading the gradebook in Ukrainian
#: gets the Ukrainian words without every route threading a locale through
#: every service that builds a roster.
request_locale: ContextVar[str] = ContextVar("request_locale", default=DEFAULT_LOCALE)


def set_request_locale(accept_language: str | None) -> Token[str]:
    """Remember the request's language; returns the token to reset it with."""
    return request_locale.set(normalize_locale(accept_language))


def label(locale: str | None = None) -> str:
    """«Deleted user» in ``locale``, or in the language of this request."""
    return LABELS.get(locale or request_locale.get(), LABELS["en"])


def shown_name(full_name: str | None, deleted_at: datetime | None) -> str | None:
    """The name to show another person: theirs, or «Deleted user»."""
    return label() if deleted_at is not None else full_name


def shown_email(email: str | None, deleted_at: datetime | None) -> str:
    """The address to show another person, or an empty string.

    Empty rather than ``None`` because most response models declare the
    email as a plain string, and the web app prints nothing for an empty one.
    """
    if deleted_at is not None:
        return ""
    return email or ""


def shown_avatar(avatar_url: str | None, deleted_at: datetime | None) -> str | None:
    return None if deleted_at is not None else avatar_url
