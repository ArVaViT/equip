#!/usr/bin/env python3
"""Tell whether the deployed edge function is older than its source in main.

Supabase does not hand back the source it is running, so an exact
byte-for-byte comparison is not available. What it does hand back is when
the function was last deployed, and git knows when the function's source
last changed. If the source changed after the last deploy, production is
running something older than main — which is the failure this exists to
catch, and the one that actually happened on 2026-09-01.

Exit codes: 0 in sync, 1 drifted or the check could not be made.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.supabase.com"
DEFAULT_REF = os.environ.get("PROJECT_REF", "rrisqutxlkamwfhcashl")
DEFAULT_SLUG = os.environ.get("FUNCTION_SLUG", "send-email")

# A deploy triggered by this workflow should be seconds old. Anything
# older than this after a deploy step means the deploy silently no-opped.
FRESH_DEPLOY_MAX_AGE_SECONDS = 15 * 60


def parse_deployed_at(function: dict) -> dt.datetime:
    """Read the deploy time off a Management API function record.

    `updated_at` is epoch milliseconds. It is the only field that moves on
    every deploy — `version` moves too but says nothing about when.
    """
    raw = function.get("updated_at")
    if raw is None:
        raise ValueError("function record has no updated_at")
    if isinstance(raw, str):
        # Tolerated in case the API ever switches to ISO 8601.
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(dt.UTC)
    return dt.datetime.fromtimestamp(raw / 1000, tz=dt.UTC)


def is_drifted(source_changed_at: dt.datetime, deployed_at: dt.datetime) -> bool:
    """True when the source moved after the last deploy.

    Equal timestamps count as in sync: a deploy that lands in the same
    second as the commit is the good case, not a drift.
    """
    return source_changed_at > deployed_at


def fetch_function(ref: str, slug: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{API}/v1/projects/{ref}/functions/{slug}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def last_source_change(paths: list[str]) -> dt.datetime:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", *paths],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not out:
        raise ValueError(f"git knows no commits touching {paths}")
    return dt.datetime.fromisoformat(out).astimezone(dt.UTC)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-ref", default=DEFAULT_REF)
    ap.add_argument("--slug", default=DEFAULT_SLUG)
    ap.add_argument(
        "--require-fresh",
        action="store_true",
        help="also fail when the deploy is not recent — used right after deploying",
    )
    args = ap.parse_args()

    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("::error::SUPABASE_ACCESS_TOKEN is not set — cannot check the deployed function.")
        return 1

    try:
        fn = fetch_function(args.project_ref, args.slug, token)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        print(f"::error::Supabase answered {exc.code} for {args.slug}: {body}")
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"::error::could not reach Supabase: {exc}")
        return 1

    deployed_at = parse_deployed_at(fn)
    source_at = last_source_change([f"supabase/functions/{args.slug}"])
    now = dt.datetime.now(tz=dt.UTC)

    print(f"function : {args.slug} v{fn.get('version')} ({fn.get('status')})")
    print(f"deployed : {deployed_at.isoformat()}")
    print(f"source   : {source_at.isoformat()} (last commit touching the function)")

    if is_drifted(source_at, deployed_at):
        behind = source_at - deployed_at
        print(
            "::error::Production is running an older version than main. "
            f"The source moved {behind} after the last deploy. "
            f"Deploy it: supabase functions deploy {args.slug} "
            f"--project-ref {args.project_ref} "
            "(or re-run the Edge Functions Deploy workflow)."
        )
        return 1

    if args.require_fresh:
        age = (now - deployed_at).total_seconds()
        if age > FRESH_DEPLOY_MAX_AGE_SECONDS:
            print(
                f"::error::The deploy step reported success but the function was "
                f"last updated {int(age)}s ago — it did not actually deploy."
            )
            return 1
        print(f"deploy is {int(age)}s old — fresh.")

    print("in sync — production matches main.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
