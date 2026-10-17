#!/usr/bin/env python3
"""Give the public objects already in Storage a cache-control a CDN can use.

Covers, avatars and lesson images were uploaded as multipart, and Storage
stored them with ``cache-control: no-cache`` (or an hour, for the oldest):
every view went through to Storage and no CDN in between kept a copy. New
uploads carry ``public, max-age=31536000, s-maxage=31536000, immutable`` since the frontend
started sending a plain body (``frontend/src/services/storage.ts``,
``PUBLIC_OBJECT_CACHE_CONTROL``). This rewrites the ones from before.

Safe because every public key is fresh and written once (``cover-<hex>``,
``avatar-<hex>``, ``content-images/<ms>-<hex>``): a year-long cache can never
serve a stale picture.

Storage has no "change the metadata" call, so each object is downloaded and
put back under the same key with the new header — same bytes, same type,
same URL. Only the two public buckets are touched; ``course-materials`` is
private and served by signed URL.

    cd backend
    SUPABASE_URL=https://rrisqutxlkamwfhcashl.supabase.co \\
    SUPABASE_SECRET_KEY="op://…" op run -- python scripts/storage_cache_control.py          # dry run
    … op run -- python scripts/storage_cache_control.py --apply                              # writes

The dry run lists what would change and touches nothing. ``--apply`` checks
each object's stored metadata after the write and exits non-zero if any did
not take. Running it twice is a no-op the second time. Keys are never printed.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

if TYPE_CHECKING:
    from collections.abc import Iterator

TARGET = "public, max-age=31536000, s-maxage=31536000, immutable"
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


def _object_url(bucket: str, path: str) -> str:
    return f"/storage/v1/object/{bucket}/{quote(path)}"


def _rewrite(client: httpx.Client, bucket: str, row: dict[str, Any]) -> None:
    got = client.get(_object_url(bucket, row["path"]))
    got.raise_for_status()
    mimetype = (row.get("metadata") or {}).get("mimetype") or got.headers.get("content-type", "")
    put = client.put(
        _object_url(bucket, row["path"]),
        content=got.content,
        headers={"cache-control": TARGET, "content-type": mimetype, "x-upsert": "true"},
    )
    put.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write; without it, only report")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SECRET_KEY are required", file=sys.stderr)
        return 2

    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=url, headers=headers, timeout=60) as client:
        failed = run(client, apply=args.apply)
    if not args.apply:
        print("dry run — nothing written; add --apply")
    return 1 if failed else 0


def run(client: httpx.Client, *, apply: bool) -> int:
    """Rewrite (or, without ``apply``, list) every stale object; return the failures."""
    failed = 0
    for bucket in BUCKETS:
        pending = [row for row in _list(client, bucket) if (row.get("metadata") or {}).get("cacheControl") != TARGET]
        print(f"{bucket}: {len(pending)} object(s) to rewrite")
        for row in pending:
            before = (row.get("metadata") or {}).get("cacheControl")
            print(f"  {row['path']}  ({before!r})")
            if not apply:
                continue
            try:
                _rewrite(client, bucket, row)
            except httpx.HTTPError as exc:
                failed += 1
                print(f"    FAILED: {type(exc).__name__}", file=sys.stderr)
        if apply:
            still = [
                row["path"]
                for row in _list(client, bucket)
                if (row.get("metadata") or {}).get("cacheControl") != TARGET
            ]
            if still:
                failed += len(still)
                print(f"{bucket}: {len(still)} object(s) still without the header: {still}", file=sys.stderr)
    return failed


if __name__ == "__main__":
    sys.exit(main())
