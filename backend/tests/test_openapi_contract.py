"""Pin the public API surface.

The snapshot at ``tests/contracts/openapi_routes.json`` captures, per
route:

* HTTP method + path
* parameter names + locations (``query`` / ``path`` / ``header``)
* response status codes
* whether the route accepts a request body

Any silent change to those — a renamed path, a dropped query param, a
status code that flipped from 200 to 204 — fails this test and shows up
in code review with the exact route line that drifted.

How to intentionally update the snapshot
-----------------------------------------

Run ``UPDATE_OPENAPI_CONTRACT=1 pytest
tests/test_openapi_contract.py`` (or invoke the inline regen below
manually) and commit the new ``openapi_routes.json``. A diff in the
snapshot file IS the API change log entry that the PR description
should explain.

Why this layer of contract instead of the full ``app.openapi()`` JSON
---------------------------------------------------------------------

The full spec is 135 KB and changes whenever a Pydantic field gets a
new ``description``. That's noise. The slim shape here is the part
that matters for a frontend or external consumer — what routes exist
and what shape they require — without the prose drift that would
nag every PR.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.main import app

_SNAPSHOT = Path(__file__).parent / "contracts" / "openapi_routes.json"


def _build_contract() -> list[dict]:
    spec = app.openapi()
    contract: list[dict] = []
    for path in sorted(spec["paths"]):
        methods = spec["paths"][path]
        for method in sorted(methods):
            route = methods[method]
            params = sorted([[p.get("name"), p.get("in")] for p in route.get("parameters", [])])
            responses = sorted(route.get("responses", {}).keys())
            body = bool(route.get("requestBody"))
            contract.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "params": params,
                    "responses": responses,
                    "body": body,
                }
            )
    return contract


def test_openapi_routes_match_snapshot():
    """If this fails, run ``UPDATE_OPENAPI_CONTRACT=1 pytest
    tests/test_openapi_contract.py`` and commit the diff."""
    current = _build_contract()

    if os.environ.get("UPDATE_OPENAPI_CONTRACT") == "1":
        _SNAPSHOT.write_text(
            json.dumps(current, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return

    assert _SNAPSHOT.exists(), (
        "OpenAPI contract snapshot is missing. Run "
        "``UPDATE_OPENAPI_CONTRACT=1 pytest tests/test_openapi_contract.py`` "
        "to bootstrap it."
    )
    stored = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))

    current_by_key = {(r["method"], r["path"]): r for r in current}
    stored_by_key = {(r["method"], r["path"]): r for r in stored}

    added = sorted(current_by_key.keys() - stored_by_key.keys())
    removed = sorted(stored_by_key.keys() - current_by_key.keys())
    diffs: list[str] = []
    for key in sorted(current_by_key.keys() & stored_by_key.keys()):
        if current_by_key[key] != stored_by_key[key]:
            diffs.append(f"{key[0]} {key[1]}: stored={stored_by_key[key]!r} current={current_by_key[key]!r}")

    if added or removed or diffs:
        msg_lines = ["OpenAPI contract drift detected:"]
        if added:
            msg_lines.append(f"  ADDED routes: {added}")
        if removed:
            msg_lines.append(f"  REMOVED routes: {removed}")
        if diffs:
            msg_lines.append("  CHANGED routes:")
            msg_lines.extend(f"    {d}" for d in diffs)
        msg_lines.append(
            "  If this is intentional, run "
            "``UPDATE_OPENAPI_CONTRACT=1 pytest tests/test_openapi_contract.py`` "
            "and commit the snapshot diff."
        )
        raise AssertionError("\n".join(msg_lines))
