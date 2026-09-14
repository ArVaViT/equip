#!/usr/bin/env python3
"""Hold the project's Auth settings to what the repository says they are.

`supabase/config/auth.production.json` lists the settings we hold on
purpose. This script compares them against the live project (`--check`,
the nightly default) or writes them (`--apply`, run by hand).

Only the keys named in that file are ever sent. Everything else in the
Auth config stays with Supabase's defaults and is not touched — a config
file that tried to own every field would go stale the first time the
platform added one.

Keys beginning with `$` are prose: comments and the reasoning behind a
value, kept beside it rather than in a wiki nobody opens.

Exit codes: 0 in sync (or applied), 1 drifted or failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.supabase.com"
CONFIG = Path(__file__).resolve().parents[2] / "supabase" / "config" / "auth.production.json"


def desired_settings(raw: dict) -> dict:
    """Strip the prose keys, leaving the settings to enforce."""
    return {k: v for k, v in raw.items() if not k.startswith("$")}


def diff(desired: dict, live: dict) -> dict[str, tuple[object, object]]:
    """Keys whose live value differs, as {key: (want, got)}.

    A key missing from the live config counts as different: we asked for a
    value and the project does not have it.
    """
    out: dict[str, tuple[object, object]] = {}
    for key, want in desired.items():
        got = live.get(key, "<absent>")
        if got != want:
            out[key] = (want, got)
    return out


def request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "equip-ci",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-ref", default=os.environ.get("PROJECT_REF", "rrisqutxlkamwfhcashl"))
    ap.add_argument("--apply", action="store_true", help="write the settings instead of checking")
    ap.add_argument("--config", default=str(CONFIG))
    args = ap.parse_args()

    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("::error::SUPABASE_ACCESS_TOKEN is not set — cannot read the Auth config.")
        return 1

    raw = json.loads(Path(args.config).read_text())
    desired = desired_settings(raw)
    if not desired:
        print("::error::the config file names no settings.")
        return 1

    try:
        live = request("GET", f"/v1/projects/{args.project_ref}/config/auth", token)
    except urllib.error.HTTPError as exc:
        print(f"::error::Supabase answered {exc.code} reading the Auth config.")
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"::error::could not reach Supabase: {exc}")
        return 1

    drifted = diff(desired, live)

    print(f"checking {len(desired)} settings against project {args.project_ref}")
    for key, want in desired.items():
        got = live.get(key, "<absent>")
        mark = " ← drift" if key in drifted else ""
        print(f"  {key:42} want={want!r:<10} live={got!r}{mark}")

    if not drifted:
        print("\nin sync — production matches the repository.")
        return 0

    if not args.apply:
        print("\n::error::Auth config drifted from supabase/config/auth.production.json:")
        for key, (want, got) in drifted.items():
            print(f"  {key}: repository says {want!r}, production has {got!r}")
        print(
            "::error::Either the change was made in the dashboard and belongs in the "
            "file, or the file is right and the Guardrails workflow should be run "
            "with apply=true."
        )
        return 1

    # PATCH carries only the drifted keys. Sending the whole desired set
    # would be harmless but noisier in the audit log.
    payload = {k: v for k, (v, _) in drifted.items()}
    print(f"\napplying {len(payload)} setting(s): {', '.join(payload)}")
    try:
        request("PATCH", f"/v1/projects/{args.project_ref}/config/auth", token, payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        print(f"::error::Supabase refused the change ({exc.code}): {body}")
        return 1

    # PATCH on this endpoint is not instant — GoTrue reloads its
    # configuration a moment later, so read back rather than trusting the
    # response body.
    after = request("GET", f"/v1/projects/{args.project_ref}/config/auth", token)
    still = diff(desired, after)
    if still:
        print("::error::settings did not take effect:")
        for key, (want, got) in still.items():
            print(f"  {key}: wanted {want!r}, still {got!r}")
        return 1

    print("applied and read back — production now matches the repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
