#!/usr/bin/env python3
"""Push ``docs/datadog/monitors/*.json`` into Datadog, in one command.

The monitors in that directory were committed on 2026-08-17 and were
still not live two days later. Not because anyone forgot: the Datadog
application key in 1Password is deliberately read-only, so the only way
to import a monitor was to open the UI and paste JSON, once per file,
by hand. The result is the worst kind of monitoring — a directory of
alert definitions that reads like coverage and fires at nothing. The
translation pipeline ran 81 days on a thinking model with five
committed monitors watching it, none of which existed.

So the import stops being a chore and becomes a command:

    cd backend
    python scripts/apply_datadog_monitors.py            # dry run, default
    python scripts/apply_datadog_monitors.py --apply    # write

It reads every JSON in ``docs/datadog/monitors/``, looks up the live
monitor **by name**, and creates it if absent or updates it if the
committed spec has drifted from what is live. Running it twice is a
no-op the second time: the first run makes Datadog match the files, and
the second finds nothing to change.

Keys come from the environment and nowhere else — ``DD_API_KEY``,
``DD_APP_KEY``, and ``DD_SITE`` (default ``us5.datadoghq.com``). Nothing
is read from a file on disk and no key value is ever printed, not even
truncated: the last rotation happened because a key reached a chat
transcript.

Scopes needed on the application key: ``monitors_read`` (to decide
create-vs-update) and ``monitors_write``. Nothing else — this script
does not touch dashboards. See ``docs/datadog/README.md``.

Exit status is 1 if any monitor failed, so CI or a human notices a
half-applied run instead of reading "done" off the last line.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

import httpx

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MONITORS_DIR = REPO_ROOT / "docs" / "datadog" / "monitors"

# The fields a committed JSON mirrors. Everything else the API returns
# (``id``, ``overall_state``, ``created_at``, ``creator``, …) is runtime
# state, not configuration, and comparing it would make every run look
# like a change.
MIRRORED_FIELDS = ("name", "type", "query", "message", "tags", "priority", "options")

# A monitor whose message opens with this word is one we know cannot
# fire — typically because the metric it queries has no emitter or no
# log-based-metric rule yet. Creating it anyway produces a monitor that
# sits in No Data forever and teaches the reader to ignore No Data.
# ``gemini-thinking-tokens-returned.json`` is the standing example.
BLOCKED_MARKER = "BLOCKED"

CREATE = "CREATE"
UPDATE = "UPDATE"
UNCHANGED = "UNCHANGED"
SKIPPED = "SKIPPED"
FAILED = "FAILED"


class SpecError(Exception):
    """A committed JSON that cannot be applied as written."""


def resolve_site(raw: str | None) -> str:
    """Turn whatever is in ``DD_SITE`` into an API hostname.

    1Password stores ``us5.datadoghq.com``; people type ``us5``. Both
    have to work, because getting this wrong fails as a 403 on a
    perfectly good key and sends the reader hunting for a scope problem
    that is not there.
    """
    site = (raw or "us5").strip()
    if not site:
        site = "us5"
    return site if "." in site else f"{site}.datadoghq.com"


def load_specs(directory: pathlib.Path) -> list[tuple[pathlib.Path, dict[str, Any]]]:
    """Parse every monitor JSON in ``directory``, sorted by filename.

    Raises ``SpecError`` on malformed JSON, a missing ``name``, or two
    files claiming the same name — the last one matters because the
    name is the key this script matches on, so a collision would make
    two files fight over one live monitor and the winner would depend
    on directory order.
    """
    specs: list[tuple[pathlib.Path, dict[str, Any]]] = []
    seen: dict[str, pathlib.Path] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SpecError(f"{path.name}: not valid JSON ({exc})") from exc
        if not isinstance(spec, dict):
            raise SpecError(f"{path.name}: expected a JSON object, got {type(spec).__name__}")
        name = spec.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SpecError(f"{path.name}: missing a non-empty 'name' — nothing to match on")
        if not spec.get("query"):
            raise SpecError(f"{path.name}: missing 'query'")
        if name in seen:
            raise SpecError(f"{path.name}: monitor name {name!r} is already claimed by {seen[name].name}")
        seen[name] = path
        specs.append((path, spec))
    return specs


def is_blocked(spec: dict[str, Any]) -> bool:
    """Does the spec declare itself unable to fire?"""
    return str(spec.get("message") or "").lstrip().startswith(BLOCKED_MARKER)


def _normalise(value: Any) -> Any:
    """Flatten the differences that are formatting, not configuration.

    Datadog answers with ``10.0`` where the file says ``10``, and tag
    order round-trips arbitrarily. Neither is a change, and reporting
    them as one would mean the script never reaches a quiet second run.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, list):
        normalised = [_normalise(item) for item in value]
        if all(isinstance(item, str) for item in normalised):
            return sorted(normalised)
        return normalised
    if isinstance(value, dict):
        return {key: _normalise(item) for key, item in value.items()}
    return value


def _differs(desired: Any, live: Any) -> bool:
    """Compare a desired value against the live one, ignoring extras.

    Nested dicts compare as a SUBSET: Datadog fills options the file
    never mentioned (``notify_by``, ``on_missing_data``, and more with
    every product release), and a strict comparison would report those
    defaults as drift on every single run — which would break
    idempotence in exactly the way that makes people stop reading the
    output. The cost is that DELETING a key from a file no longer
    reverts it in Datadog; say so out loud rather than let it surprise
    someone, and remove such a setting in the UI as well.
    """
    if isinstance(desired, dict) and isinstance(live, dict):
        return any(key not in live or _differs(value, live[key]) for key, value in desired.items())
    return _normalise(desired) != _normalise(live)


def _render(value: Any) -> str:
    if isinstance(value, str):
        return value if len(value) <= 120 else value[:117] + "..."
    return json.dumps(_normalise(value), sort_keys=True, ensure_ascii=False)


def diff_spec(desired: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """Human-readable per-field diff, empty when the live monitor already
    matches the committed one."""
    lines: list[str] = []
    for field in MIRRORED_FIELDS:
        if field not in desired:
            continue
        if not _differs(desired[field], live.get(field)):
            continue
        lines.append(f"    {field}:")
        lines.append(f"      live: {_render(live.get(field))}")
        lines.append(f"      file: {_render(desired[field])}")
    return lines


def payload_for(spec: dict[str, Any]) -> dict[str, Any]:
    """The body to send — the mirrored fields and nothing else, so a
    stray ``id`` pasted in from a UI export cannot retarget the call."""
    return {field: spec[field] for field in MIRRORED_FIELDS if field in spec}


def index_by_name(monitors: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group live monitors by name. A name can legitimately be
    duplicated in Datadog — the UI never stops you — and this script
    refuses to guess which one a file means."""
    index: dict[str, list[dict[str, Any]]] = {}
    for monitor in monitors:
        index.setdefault(str(monitor.get("name", "")), []).append(monitor)
    return index


def fetch_live(client: httpx.Client) -> list[dict[str, Any]]:
    response = client.get("/api/v1/monitor")
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, list):
        raise SpecError(f"unexpected monitor list response: {type(body).__name__}")
    return body


def apply_one(
    client: httpx.Client,
    path: pathlib.Path,
    spec: dict[str, Any],
    live_by_name: dict[str, list[dict[str, Any]]],
    *,
    write: bool,
) -> tuple[str, list[str]]:
    """Decide (and optionally perform) what should happen to one file.

    Returns the verdict and the lines to print under the filename.
    """
    name = spec["name"]
    if is_blocked(spec):
        return SKIPPED, [f"    {name}", "    message opens with BLOCKED — it cannot fire yet, so it is not created"]

    matches = live_by_name.get(name, [])
    if len(matches) > 1:
        ids = ", ".join(str(m.get("id")) for m in matches)
        return FAILED, [f"    {name}", f"    {len(matches)} live monitors share this name ({ids}) — resolve in the UI"]

    if not matches:
        if not write:
            return CREATE, [f"    {name}"]
        response = client.post("/api/v1/monitor", json=payload_for(spec))
        if response.is_error:
            return FAILED, [f"    {name}", f"    POST {response.status_code}: {response.text[:300]}"]
        return CREATE, [f"    {name}", f"    created as id {response.json().get('id')}"]

    live = matches[0]
    changes = diff_spec(spec, live)
    if not changes:
        return UNCHANGED, []
    if not write:
        return UPDATE, [f"    {name} (id {live.get('id')})", *changes]
    response = client.put(f"/api/v1/monitor/{live['id']}", json=payload_for(spec))
    if response.is_error:
        return FAILED, [f"    {name}", f"    PUT {response.status_code}: {response.text[:300]}"]
    return UPDATE, [f"    {name} (id {live.get('id')})", *changes]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write to Datadog; without it the script only reports what it would do",
    )
    parser.add_argument(
        "--dir",
        type=pathlib.Path,
        default=MONITORS_DIR,
        help=f"directory of monitor JSONs (default: {MONITORS_DIR})",
    )
    args = parser.parse_args()

    api_key = os.environ.get("DD_API_KEY")
    app_key = os.environ.get("DD_APP_KEY")
    missing = [name for name, value in (("DD_API_KEY", api_key), ("DD_APP_KEY", app_key)) if not value]
    if missing:
        # Named separately on purpose: the API key and the application
        # key are different objects with different lifetimes, and
        # "Datadog rejected the request" reads identically whichever one
        # is absent.
        print(f"missing environment: {', '.join(missing)}", file=sys.stderr)
        print("DD_API_KEY is the org's ingest key; DD_APP_KEY is a per-user key carrying the scopes.", file=sys.stderr)
        return 2

    site = resolve_site(os.environ.get("DD_SITE"))

    try:
        specs = load_specs(args.dir)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not specs:
        print(f"no monitor JSONs found in {args.dir}", file=sys.stderr)
        return 1

    mode = "APPLY" if args.apply else "DRY RUN (pass --apply to write)"
    print(f"{mode} — {len(specs)} spec(s) against https://api.{site}\n")

    headers = {"DD-API-KEY": api_key or "", "DD-APPLICATION-KEY": app_key or "", "Content-Type": "application/json"}
    tally: dict[str, int] = {CREATE: 0, UPDATE: 0, UNCHANGED: 0, SKIPPED: 0, FAILED: 0}

    with httpx.Client(base_url=f"https://api.{site}", headers=headers, timeout=30.0) as client:
        try:
            live_by_name = index_by_name(fetch_live(client))
        except (httpx.HTTPError, SpecError) as exc:
            # Deliberately does not echo the exception's request headers.
            print(f"error: could not list monitors ({type(exc).__name__})", file=sys.stderr)
            print("A 403 here usually means the application key lacks monitors_read.", file=sys.stderr)
            return 1

        for path, spec in specs:
            try:
                verdict, lines = apply_one(client, path, spec, live_by_name, write=args.apply)
            except httpx.HTTPError as exc:
                verdict, lines = FAILED, [f"    {spec['name']}", f"    request failed: {type(exc).__name__}"]
            tally[verdict] += 1
            if verdict == UNCHANGED:
                continue
            print(f"{verdict}  {path.name}")
            for line in lines:
                print(line)
            print()

    summary = "  ".join(f"{verdict.lower()}={count}" for verdict, count in tally.items())
    print(summary)
    if tally[FAILED]:
        return 1
    if not args.apply and (tally[CREATE] or tally[UPDATE]):
        print("\nnothing was written — re-run with --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
