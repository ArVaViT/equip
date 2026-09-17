"""Keep bearer secrets out of anything this process writes to a log.

On 2026-09-16 Datadog held invitation tokens in three shapes, all from
this backend or its platform: the access line
(``GET /api/v1/invitations/token/<token> 200 12ms``), the text of a
SQLAlchemy error (``[parameters: {'token_1': '<token>'}]``), and the
Vercel request line. An invitation token is a bearer credential: whoever
reads it can see the invited address and, signed in under that address,
take the role it carries. A log index is read by more people, for longer,
than the link was ever meant to reach.

This module is the one place that decides what counts as a secret in a
string. It is applied by the formatter every log handler shares
(``app.core.logging.setup_logging``), so a log call does not have to
remember it -- the access line and the database-error line are covered
because they are log records, not because somebody wrapped them.

What is a secret here, and what is deliberately not:

* **Secret** -- an invitation token in the path of the legacy preview
  route; any query or fragment parameter that carries a credential
  (``token``, ``access_token``, ``refresh_token``, ``provider_token``,
  ``provider_refresh_token``, ``id_token``, ``token_hash``, ``code``) --
  the iCal feed takes its signed token that way, and Supabase's auth
  redirects put the session there; any JWT, wherever it appears; the
  value after ``Bearer``; the password in a connection string; and the
  bound parameters SQLAlchemy prints into an error, which carry tokens,
  email addresses and answers alike.
* **Not secret** -- ``/certificates/verify/{certificate_number}``: the
  number is printed on the certificate so that a stranger can check it,
  which is the whole point of the route. Organization and legal-document
  slugs are public names. Resource ids are not credentials: every route
  that takes one checks who is asking.
"""

from __future__ import annotations

import re

#: What a redacted value is replaced with. Short, greppable, and not
#: something a real token could ever be.
REDACTED = "[redacted]"

#: Path segments whose *next* segment is a credential. Anchored on the
#: route shape, not on "the thing looks random", so an id is never
#: mistaken for a token and a token is never missed for looking tidy.
_SECRET_PATH = re.compile(r"(/invitations/token/)[^/?#\s'\"]+")

#: Query or fragment parameters that carry a credential. The lookbehind
#: pins the name to a parameter boundary, so ``error_code=`` and
#: ``token_type=`` are left alone while ``code=`` and ``token=`` are not.
_SECRET_PARAMS = (
    "token",
    "access_token",
    "refresh_token",
    "provider_token",
    "provider_refresh_token",
    "id_token",
    "token_hash",
    "code",
)
_SECRET_PARAM = re.compile(r"(?<=[?&#])(" + "|".join(_SECRET_PARAMS) + r")=[^&#\s'\"]+")

#: A JWT anywhere in the text: three base64url parts, the first two
#: starting ``eyJ`` (``{"``). The iCal feed token is one of these.
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

#: The password in a connection string (``postgresql://user:pw@host``),
#: which an engine that fails to connect prints back.
_URL_PASSWORD = re.compile(r"(://[^:/@\s]+:)[^@\s]+(@)")

_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")

#: SQLAlchemy renders bound values into ``str(exc)`` as
#: ``[parameters: {...}]`` (or a tuple / list for executemany). The engine
#: is built with ``hide_parameters=True`` so this should never appear;
#: this is what keeps it out when an error comes from an engine that was
#: not -- a script, a test, a future second engine.
_SQL_PARAMETERS = re.compile(r"\[parameters: .*?\](?=\s*(?:\n|\(Background on this error|$))", re.DOTALL)


def redact_secrets(text: str) -> str:
    """``text`` with every credential this module knows about replaced."""
    if not text:
        return text
    text = _SQL_PARAMETERS.sub(f"[parameters: {REDACTED}]", text)
    text = _SECRET_PATH.sub(rf"\g<1>{REDACTED}", text)
    text = _SECRET_PARAM.sub(rf"\g<1>={REDACTED}", text)
    text = _JWT.sub(REDACTED, text)
    text = _URL_PASSWORD.sub(rf"\g<1>{REDACTED}\g<2>", text)
    return _BEARER.sub(rf"\g<1>{REDACTED}", text)
