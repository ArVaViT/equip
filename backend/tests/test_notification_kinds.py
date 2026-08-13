"""Every notification kind the product writes must be a kind it knows.

The bell was returning **500** in production. `grades.py` writes
`retake_requested`; the response model's `Literal` did not list it; FastAPI
refused to serialise the list; every user holding one of those notifications
got an error instead of their notifications. Seven occurrences in six hours,
and nothing failed in CI because no test ever created one and then read the
list back.

The allowlist was also too wide — `course_update` and `enrollment_confirmed`
were in it and in nobody's write path — which is the same defect from the
other side: a list nobody checks drifts in both directions.

So the check moved to where the mistake is actually made. This walks the call
sites with `ast` rather than asserting a hand-written list, because a
hand-written list is exactly what failed.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.schemas.notification import NOTIFICATION_TYPES

APP = Path(__file__).resolve().parent.parent / "app"
EMITTERS = {"create_notification", "create_notifications_bulk"}


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "literal"`, so a kind passed by constant resolves."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        out[target.id] = node.value.value
    return out


def _emitted_kinds() -> dict[str, list[str]]:
    """kind -> the files that write it."""
    found: dict[str, list[str]] = {}
    # Constants can live in a different module from the call (the retake kind
    # is defined in `certificate_readiness` and used in `grades`), so collect
    # every module-level string constant in the app first.
    constants: dict[str, str] = {}
    trees: dict[Path, ast.Module] = {}
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        trees[path] = tree
        constants.update(_module_constants(tree))

    for path, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name not in EMITTERS:
                continue
            for kw in node.keywords:
                if kw.arg != "type":
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    kind = kw.value.value
                elif isinstance(kw.value, ast.Name) and kw.value.id in constants:
                    kind = constants[kw.value.id]
                else:
                    # A computed kind cannot be checked here; fail loudly rather
                    # than pass silently, which is how the last one got through.
                    raise AssertionError(
                        f"{path.name}: notification `type` is not a literal or a "
                        f"module constant, so it cannot be checked statically"
                    )
                found.setdefault(kind, []).append(path.name)
    return found


def test_every_emitted_kind_is_known() -> None:
    emitted = _emitted_kinds()
    assert emitted, "found no notification call sites — the scan is broken, not the code"
    unknown = {k: v for k, v in emitted.items() if k not in NOTIFICATION_TYPES}
    assert not unknown, (
        "These kinds are written to the database but missing from "
        f"NOTIFICATION_TYPES: {unknown}. That is exactly the shape of the bug "
        "that made GET /api/v1/notifications answer 500 in production."
    )


def test_no_kind_is_declared_that_nobody_writes() -> None:
    emitted = set(_emitted_kinds())
    orphans = NOTIFICATION_TYPES - emitted
    assert not orphans, (
        f"NOTIFICATION_TYPES declares {sorted(orphans)}, which no call site "
        "emits. An allowlist nobody checks drifts in both directions — this is "
        "the half that leaves dead entries behind."
    )


def test_the_response_survives_a_kind_it_has_never_seen(student_client, db) -> None:
    """A future kind must degrade, not take the whole list down with it."""
    from app.models.notification import Notification

    from .conftest import STUDENT_ID

    db.add(
        Notification(
            user_id=STUDENT_ID,
            type="some_kind_invented_next_year",
            title="Заголовок",
            message="Текст",
        )
    )
    db.commit()

    response = student_client.get("/api/v1/notifications")

    assert response.status_code == 200
    kinds = [item["type"] for item in response.json()["items"]]
    assert "some_kind_invented_next_year" in kinds
