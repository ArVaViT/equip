"""The rule, guarded structurally rather than case by case.

"No spare language" was implemented once, in ``pick_overlay_value``,
and then undone at five call sites with `or mod.title` — the source
column, in the author's language. A German reader opening a Russian
course got the whole tree in Russian while every test passed, because
every test asserted the resolver and none asserted the callers.

Two shapes are outlawed here:

* ``loc.pick(...) or <something>`` — the resolver said "this language
  does not have it" and the caller answered "then use the author's".
  Falling back to ``""`` is fine; falling back to a value is not.
* ``fallback="source_then_any"`` outside the editor surfaces. Those
  genuinely need it — a teacher must see their own lesson whatever
  language it is in — and they are listed by name, so adding a sixth
  is a decision somebody makes on purpose.

Written as an AST walk for the same reason ``test_notification_kinds``
is: a hand-maintained list of "the places that resolve text" is exactly
what drifted.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

# Where a fallback to the source language is the correct answer: the
# people who must see their own material whatever language it is in.
EDITOR_SURFACES = {
    "app/api/v1/blocks.py",
    "app/services/certificate_service.py",
    # The grading queue. A marker is not a reader being served content —
    # they are being asked to judge an answer to a specific question, and
    # a blank where the question should be hides the thing they are
    # judging. It resolves at the teacher's own language first; this is
    # only the last resort. (Before this it was pinned to English at the
    # call site, which is neither.)
    "app/api/v1/quizzes/grading.py",
}


def _call_name(node: ast.Call) -> str:
    return node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")


def _pick_calls_with_a_fallback_value() -> list[str]:
    offences: list[str] = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # `<pick call> or <x>` — the `or` is what puts the other
            # language back.
            if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or):
                continue
            first = node.values[0]
            if not isinstance(first, ast.Call) or _call_name(first) not in {"pick", "pick_overlay_value"}:
                continue
            for alternative in node.values[1:]:
                # `or ""` is the honest one: nothing to show, say nothing.
                if isinstance(alternative, ast.Constant) and alternative.value in ("", None):
                    continue
                offences.append(f"{path.relative_to(APP.parent)}:{node.lineno}")
    return offences


def _source_fallbacks_outside_the_editor() -> list[str]:
    offences: list[str] = []
    for path in APP.rglob("*.py"):
        relative = str(path.relative_to(APP.parent))
        if relative in EDITOR_SURFACES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "fallback":
                    continue
                if isinstance(keyword.value, ast.Constant) and keyword.value.value == "source_then_any":
                    offences.append(f"{relative}:{node.lineno}")
    return offences


def test_no_resolver_falls_back_to_the_authors_language():
    offences = _pick_calls_with_a_fallback_value()
    assert not offences, "these would serve a reader text in a language they did not choose: " + ", ".join(offences)


def test_the_source_language_fallback_stays_where_it_belongs():
    offences = _source_fallbacks_outside_the_editor()
    assert not offences, (
        "a reader surface asking for the source language: "
        + ", ".join(offences)
        + " — if it is genuinely an editor surface, add it to EDITOR_SURFACES and say why"
    )


def test_the_guard_can_actually_see_the_shape_it_forbids():
    # A guard that matches nothing passes forever. This is the exact
    # line that was in `build_localized_course_response_with_tree`.
    tree = ast.parse('mt = loc.pick("module", str(mod.id), "title", mod.title) or mod.title')
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BoolOp)
        and isinstance(node.op, ast.Or)
        and isinstance(node.values[0], ast.Call)
        and _call_name(node.values[0]) == "pick"
        and not isinstance(node.values[1], ast.Constant)
    ]
    assert found, "the AST guard no longer recognises the pattern it exists to forbid"
