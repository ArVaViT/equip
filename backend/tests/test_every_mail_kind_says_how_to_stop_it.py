"""Every kind of course mail says, in every language, how to stop it.

The certificate mail shipped with its unsubscribe line reading
``email.unsubscribe.certificate_decided`` — the key itself, because the
label had not been written and ``t()`` falls back to the key. This keeps a
new kind from going out without its words.
"""

from __future__ import annotations

import pytest

from app.core.i18n import t
from app.services.email.course_mail import KINDS


@pytest.mark.parametrize("locale", ["en", "ru", "de", "uk"])
@pytest.mark.parametrize("kind", KINDS)
def test_the_unsubscribe_line_is_written(kind: str, locale: str) -> None:
    key = f"email.unsubscribe.{kind}"
    assert t(locale, key) != key
