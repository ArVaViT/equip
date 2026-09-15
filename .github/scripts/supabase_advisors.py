#!/usr/bin/env python3
"""Turn Supabase's advisors into a gate that only speaks when it matters.

Supabase emails its advisor findings weekly and lists them in the
dashboard. Both are easy to stop reading, and two lessons from this
project say why a raw feed is the wrong tool:

* the advisor describes the WORST case, not the measured one. Its
  wording for eight tables without RLS was "read, edit, and delete";
  the measurement showed `anon` held SELECT only.
* on 2026-09-13 the performance advisor reported 17 unindexed foreign
  keys — every one of them on a table holding ZERO rows. Acting on that
  list would have added 17 indexes to a database that already had 32
  unused ones.

So this gate applies judgement the feed cannot:

* an unindexed foreign key matters once its table is big enough for a
  sequential scan to hurt (`ROW_THRESHOLD`), not before;
* findings we have examined and accepted live in `ACCEPTED` with the
  reason written down, and stop being noise;
* anything else at WARN or above fails the run.

Exit codes: 0 nothing to act on, 1 something needs a person.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.supabase.com"

# Below this many live rows, a missing index on a foreign key is not a
# performance problem: the planner reads the whole table faster than it
# would walk an index, and the index would only add write cost and noise
# to the "unused index" list.
ROW_THRESHOLD = 1_000

# Findings examined and deliberately accepted. Key is the advisor's lint
# name; the value is why, so the next person does not re-litigate it.
ACCEPTED: dict[str, str] = {
    "rls_enabled_no_policy": (
        "Deliberate deny-all. RLS is on with no policy, the backend reaches these "
        "tables with the service role, and no client reads them directly."
    ),
    "auth_otp_long_expiry": (
        "mailer_otp_exp is 86400 on purpose: a one-hour link was expiring before "
        "people opened their mail, which broke six of seven sign-ups."
    ),
    # `anon_security_definer_function_executable` used to be accepted here, on the
    # grounds that revoking EXECUTE would break the public catalogue. That was
    # wrong, and the entry is gone rather than corrected: the catalogue is served
    # by the backend on the service role, and all three policies calling these
    # helpers (courses_select_published, cohorts_select_own_organization,
    # certificates_select_own_or_reviewer) are declared TO authenticated, so anon
    # never evaluates them. EXECUTE was revoked from anon on 2026-09-15
    # (20260915030000_anon_loses_execute_on_three_definer_functions) and the
    # catalogue still answers. If the finding ever returns, it is a real
    # regression — let it through.
    "authenticated_security_definer_function_executable": (
        "can_teach / current_organization_id / is_platform_staff take no arguments, "
        "read auth.uid() and answer about the caller. authenticated callers need "
        "EXECUTE for the policies that call them to run at all."
    ),
    "unused_index": (
        "Indexes are judged when there is traffic to judge them by. With the "
        "largest affected table under a thousand rows, 'unused' means 'not needed "
        "yet', not 'wrong'."
    ),
    "auth_db_connections_absolute": (
        "Informational: the pool sizing was measured on 2026-08-12 (5+5, timeout 10s) "
        "against a chapter page making seven parallel calls."
    ),
}

SEVERITY_ORDER = {"INFO": 0, "WARN": 1, "ERROR": 2}


def fetch(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "equip-ci"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)


def post(path: str, token: str, body: dict) -> dict | list:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "equip-ci",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)


def lints(payload: dict | list) -> list[dict]:
    if isinstance(payload, dict):
        return payload.get("lints", [])
    return payload


def table_of(finding: dict) -> str | None:
    meta = finding.get("metadata") or {}
    return meta.get("name")


def should_report(
    finding: dict,
    row_counts: dict[str, int] | None,
    threshold: int = ROW_THRESHOLD,
) -> bool:
    """Does this finding need a person today?

    The row-count rule applies only to unindexed foreign keys: that is the
    finding whose cost scales with table size. Everything else is judged on
    its name and severity alone.

    `row_counts` of None means the sizes could not be read at all. The
    foreign-key rule is then skipped rather than fired: firing it would
    turn every run into the same seventeen lines nobody can act on, which
    is how a gate stops being read. The caller says so out loud instead —
    see `main`. A table simply missing from a set we DID read is different:
    it gets reported, because we could measure and it was not there.
    """
    name = finding.get("name", "")
    if name in ACCEPTED:
        return False
    if SEVERITY_ORDER.get((finding.get("level") or "INFO").upper(), 0) < SEVERITY_ORDER["WARN"]:
        if name != "unindexed_foreign_keys":
            return False
    if name == "unindexed_foreign_keys":
        if row_counts is None:
            return False
        table = table_of(finding)
        return row_counts.get(table, threshold) >= threshold if table else True
    return True


ROW_COUNTS_SQL = "select relname, n_live_tup from pg_stat_user_tables order by n_live_tup desc"


def fetch_row_counts(ref: str, token: str) -> dict[str, int] | None:
    """Live row counts, or None when they cannot be had.

    Read through the Management API rather than the CLI: `supabase db query`
    needs a linked project and a database password, neither of which CI has,
    and a silent failure there previously turned this gate into seventeen
    lines of noise.
    """
    try:
        payload = post(f"/v1/projects/{ref}/database/query", token, {"query": ROW_COUNTS_SQL})
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return None
    rows = payload if isinstance(payload, list) else payload.get("result", payload.get("rows", []))
    if not isinstance(rows, list):
        return None
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("relname")
        value = row.get("n_live_tup")
        if isinstance(name, str) and isinstance(value, (int, float)):
            counts[name] = int(value)
    return counts or None


def parse_row_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        line = row.get("line") or ""
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        try:
            counts[name] = int(value)
        except ValueError:
            continue
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-ref", default=os.environ.get("PROJECT_REF", "rrisqutxlkamwfhcashl"))
    ap.add_argument("--row-counts", help="JSON list of {line: 'table=rows'}; skips the live query")
    args = ap.parse_args()

    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("::error::SUPABASE_ACCESS_TOKEN is not set — cannot read advisors.")
        return 1

    if args.row_counts:
        row_counts: dict[str, int] | None = parse_row_counts(json.loads(args.row_counts))
    else:
        row_counts = fetch_row_counts(args.project_ref, token)
    if row_counts is None:
        print(
            "::warning::Could not read table sizes, so the unindexed-foreign-key "
            "rule is skipped this run. Everything else is still checked."
        )
    else:
        print(f"table sizes read for {len(row_counts)} tables.")

    actionable: list[dict] = []
    accepted_count = 0
    quiet_count = 0

    for kind in ("security", "performance"):
        try:
            payload = fetch(f"/v1/projects/{args.project_ref}/advisors/{kind}", token)
        except urllib.error.HTTPError as exc:
            print(f"::error::Supabase answered {exc.code} for the {kind} advisor.")
            return 1
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"::error::could not reach Supabase: {exc}")
            return 1

        for finding in lints(payload):
            if finding.get("name") in ACCEPTED:
                accepted_count += 1
            elif should_report(finding, row_counts):
                actionable.append({**finding, "advisor": kind})
            else:
                quiet_count += 1

    print(f"advisors: {accepted_count} accepted, {quiet_count} below threshold, {len(actionable)} need a person.")

    if not actionable:
        print("nothing to act on.")
        return 0

    print("\n::group::Findings")
    for f in actionable:
        table = table_of(f) or "-"
        print(f"  [{f.get('level')}] {f.get('advisor')}/{f.get('name')} on {table}")
        detail = (f.get("detail") or "").replace("\\`", "`")
        print(f"      {detail[:300]}")
    print("::endgroup::")
    print(
        "::error::Supabase advisors report findings that are past the point of "
        "being deferred. Read them above, then either fix them or record the "
        "decision in ACCEPTED in this script with the reason."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
