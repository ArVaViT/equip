#!/usr/bin/env python3
"""Give the public objects already in Storage a cache-control a CDN can use.

Covers, avatars and lesson images were uploaded as multipart without a
``cacheControl`` field, and Storage stored them with ``cache-control:
no-cache``: every view went through to Storage and no CDN in between kept a
copy. New uploads carry ``max-age=31536000`` since the frontend started
sending the field (``frontend/src/services/storage.ts``,
``PUBLIC_OBJECT_CACHE_CONTROL``). This rewrites the ones from before.

Safe because every public key is fresh and written once (``cover-<hex>``,
``avatar-<hex>``, ``content-images/<ms>-<hex>``): a year-long cache can never
serve a stale picture.

Storage has no "change the metadata" call, so each object is downloaded and
put back under the same key — same bytes, same type, same URL — as a
multipart upload with ``cacheControl=31536000``. That field is the one form
Storage composes the header from itself (``max-age=<seconds>``). The first
version of this script sent a plain body with a hand-written
``cache-control`` header instead; Storage echoed it into the row's metadata
and kept serving ``no-cache`` (production, 2026-10-17), so the row's
metadata is not trusted here: after each write the object is fetched
through its public URL, past the CDN, and the header it answers with is
what counts.

Only the two public buckets are touched; ``course-materials`` is private
and served by signed URL. An object whose type the bucket no longer
accepts (the SVG diagrams in ``course-assets``, uploaded before the bucket
was limited to raster images) cannot be put back and is skipped, by name,
rather than counted as a failure.

    cd backend
    SUPABASE_URL=https://rrisqutxlkamwfhcashl.supabase.co \\
    SUPABASE_SECRET_KEY="op://…" op run -- python scripts/storage_cache_control.py          # dry run
    … op run -- python scripts/storage_cache_control.py --apply                              # writes
    … op run -- python scripts/storage_cache_control.py --apply --only course-assets/<key>   # one object

The dry run lists what would change and touches nothing. ``--apply`` exits
non-zero if any object still answers without the header. Running it twice
is a no-op the second time.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

if TYPE_CHECKING:
    from collections.abc import Iterator

MAX_AGE_SECONDS = 31536000
TARGET = f"max-age={MAX_AGE_SECONDS}"
BUCKETS = ("course-assets", "avatars")
PAGE = 100


def _list(client: httpx.Client, bucket: str, prefix: str = "") -> Iterator[dict[str, Any]]:
    """Every object under ``prefix``, descending into folders."""
    offset = 0
    while True:
        response = client.post(
            f"/storage/v1/object/list/{bucket}",
            json={"prefix": prefix, "limit": PAGE, "offset": offset, "sortBy": {"column": "name", "order": "asc"}},
        )
        response.raise_for_status()
        rows: list[dict[str, Any]] = response.json()
        for row in rows:
            path = f"{prefix}{row['name']}"
            if row.get("id") is None:  # a folder
                yield from _list(client, bucket, f"{path}/")
            else:
                yield {**row, "path": path}
        if len(rows) < PAGE:
            return
        offset += PAGE


def _allowed_mime_types(client: httpx.Client, bucket: str) -> list[str] | None:
    """The bucket's ``allowed_mime_types``; ``None`` when it accepts anything."""
    response = client.get(f"/storage/v1/bucket/{bucket}")
    response.raise_for_status()
    allowed = response.json().get("allowed_mime_types")
    return list(allowed) if allowed else None


def _object_url(bucket: str, path: str) -> str:
    return f"/storage/v1/object/{bucket}/{quote(path)}"


def _mimetype(row: dict[str, Any], fallback: str = "") -> str:
    return str((row.get("metadata") or {}).get("mimetype") or fallback)


def _rewrite(client: httpx.Client, bucket: str, row: dict[str, Any]) -> None:
    got = client.get(_object_url(bucket, row["path"]))
    got.raise_for_status()
    mimetype = _mimetype(row, got.headers.get("content-type", "application/octet-stream"))
    # Fields must come before the file part: Storage reads ``cacheControl``
    # off the part it has already seen when the file arrives. httpx encodes
    # ``data`` before ``files``.
    put = client.put(
        _object_url(bucket, row["path"]),
        data={"cacheControl": str(MAX_AGE_SECONDS)},
        files={"": (row["path"].rsplit("/", 1)[-1], got.content, mimetype)},
        headers={"x-upsert": "true"},
    )
    put.raise_for_status()


def served_cache_control(client: httpx.Client, bucket: str, path: str) -> str:
    """The ``cache-control`` the public URL answers with, fetched past any CDN copy."""
    response = client.get(
        f"/storage/v1/object/public/{bucket}/{quote(path)}",
        params={"v": uuid.uuid4().hex},
        headers={"cache-control": "no-cache"},
    )
    response.raise_for_status()
    return response.headers.get("cache-control", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write; without it, only report")
    parser.add_argument("--only", metavar="BUCKET/KEY", help="touch this one object and nothing else")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SECRET_KEY are required", file=sys.stderr)
        return 2
    if args.only and args.only.split("/", 1)[0] not in BUCKETS:
        print(f"--only must start with one of {', '.join(BUCKETS)}", file=sys.stderr)
        return 2

    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=url, headers=headers, timeout=60) as client:
        failed = run(client, apply=args.apply, only=args.only)
    if not args.apply:
        print("dry run — nothing written; add --apply")
    return 1 if failed else 0


def run(client: httpx.Client, *, apply: bool, only: str | None = None) -> int:
    """Rewrite (or, without ``apply``, list) every stale object; return the failures."""
    failed = 0
    for bucket in BUCKETS:
        if only and not only.startswith(f"{bucket}/"):
            continue
        allowed = _allowed_mime_types(client, bucket)
        rows = [row for row in _list(client, bucket) if (row.get("metadata") or {}).get("cacheControl") != TARGET]
        if only:
            rows = [row for row in rows if f"{bucket}/{row['path']}" == only]
        refused = [row for row in rows if allowed is not None and _mimetype(row) not in allowed]
        pending = [row for row in rows if row not in refused]
        print(f"{bucket}: {len(pending)} object(s) to rewrite")
        for row in refused:
            print(
                f"  skipped {row['path']}: {_mimetype(row) or 'unknown type'} is not in the bucket's allowed_mime_types"
            )
        for row in pending:
            before = (row.get("metadata") or {}).get("cacheControl")
            print(f"  {row['path']}  ({before!r})")
            if not apply:
                continue
            try:
                _rewrite(client, bucket, row)
                served = served_cache_control(client, bucket, row["path"])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 415:
                    print(f"    skipped: Storage refused the type ({_mimetype(row) or 'unknown'})")
                    continue
                failed += 1
                print(f"    FAILED: HTTP {exc.response.status_code} on {exc.request.method}", file=sys.stderr)
                continue
            except httpx.HTTPError as exc:
                failed += 1
                print(f"    FAILED: {type(exc).__name__}", file=sys.stderr)
                continue
            if TARGET in served:
                print(f"    now served with {served!r}")
            else:
                failed += 1
                print(f"    FAILED: written, but still served with {served!r}", file=sys.stderr)
    return failed


if __name__ == "__main__":
    sys.exit(main())
