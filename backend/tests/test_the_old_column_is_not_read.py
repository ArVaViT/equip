"""Nothing in the application reads ``profiles.organization_id`` any more.

The column is deprecated (2026-10-03): membership is a row in
``organization_members`` and ``app.services.memberships`` is the one place
that reads it. Until the column is dropped it is the easiest thing in the
codebase to compare against by habit — ``user.organization_id ==
course.organization_id`` reads perfectly well and is wrong for everyone
with a second membership — and a review will not catch every one. This
does: it greps.

What is allowed: the model declaring the column, and ``grant_membership``
writing it (the first organization, when empty) so the previous backend
release still works on rollback. Both go with the column.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

#: ``<something>.organization_id`` where the something is a person, or the
#: column itself on the model class.
_PERSON = r"(?:user|current_user|teacher|director|reviewer|person|viewer|student|admin|approver|actor|caller|me|u|p)"
_READS = re.compile(rf"\b{_PERSON}\.organization_id\b|\bUser\.organization_id\b")

#: File -> the exact lines that may mention it, each with the reason.
ALLOWED: dict[str, set[str]] = {
    "models/user.py": {
        # The declaration itself, deprecated in its own docstring.
        "organization_id: Mapped[uuid.UUID | None] = mapped_column(",
    },
    "services/memberships.py": {
        # The transitional dual write, and nothing else.
        "if user.organization_id is None:",
        "user.organization_id = organization_id",
    },
}


def test_the_application_does_not_read_the_deprecated_column() -> None:
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not _READS.search(line):
                continue
            if any(allowed in line for allowed in ALLOWED.get(relative, set())):
                continue
            offenders.append(f"{relative}:{number}: {line.strip()}")
    assert not offenders, "profiles.organization_id is deprecated; ask app.services.memberships instead:\n" + "\n".join(
        offenders
    )


def test_every_allowed_line_still_exists() -> None:
    """An allow-list entry whose line is gone is a stale exemption."""
    stale: list[str] = []
    for relative, lines in ALLOWED.items():
        text = (APP / relative).read_text(encoding="utf-8")
        stale.extend(f"{relative}: {line}" for line in lines if line not in text)
    assert not stale, "Listed as allowed but no longer present:\n" + "\n".join(stale)
