"""
One-off: move course ``image_url`` from legacy Vercel static files to Supabase
``course-assets`` (same layout as the teacher UI), so course marketing images are not committed as static app assets.

Run with ``.env`` loaded (DATABASE_URL, SUPABASE_SERVICE_ROLE_KEY):

  cd backend && python scripts/migrate_static_course_covers_to_storage.py
"""

from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.core.config import settings  # noqa: E402
from app.core.course_cover_upload import upload_course_cover_bytes  # noqa: E402

# Vercel / local dev: static PNGs from ``frontend/public/`` (not Supabase)
_LEGACY_HOST_PARTS = ("vercel.app", "localhost", "127.0.0.1")
_LEGACY_PREFIX = ("/acts_", "/covers/")


def _is_legacy_static_cover_url(url: str) -> bool:
    u = (url or "").strip()
    if not u or u.startswith("/img/course-assets/"):
        return False
    if u.startswith("http://") or u.startswith("https://"):
        p = urlparse(u)
        if not any(s in p.netloc for s in _LEGACY_HOST_PARTS):
            return False
        path = p.path or ""
    else:
        path = (u if u.startswith("/") else f"/{u}").split("?", 1)[0]
    pl = path.lower()
    if not pl.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")):
        return False
    return pl.startswith(_LEGACY_PREFIX) or pl == "/acts_course_banner.png" or "covers/" in pl


def _ext_from_path(path: str) -> str:
    base = path.rsplit(".", 1)
    if len(base) < 2:
        return "png"
    e = base[-1].lower()
    if e == "jpeg":
        return "jpg"
    if e in ("png", "jpg", "webp", "gif"):
        return e
    return "png"


def _fetch_bytes(url: str) -> tuple[bytes, str, str]:
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.content
        ct = r.headers.get("content-type", "").split(";")[0].strip()
        if not ct or ct == "application/octet-stream" or "text" in ct:
            guessed, _ = mimetypes.guess_type(url)
            ct = guessed or "image/png"
    return data, ct, _ext_from_path(urlparse(url).path or url)


def main() -> None:
    k = settings.SUPABASE_SERVICE_ROLE_KEY
    if not k:
        print("Set SUPABASE_SERVICE_ROLE_KEY in .env", file=sys.stderr)
        raise SystemExit(1)

    eng = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    with eng.connect() as c:
        rows = c.execute(
            text(
                "SELECT id::text, image_url FROM courses WHERE deleted_at IS NULL AND image_url IS NOT NULL",
            ),
        ).fetchall()

    updated = 0
    for cid, iurl in rows:
        s = (iurl or "").strip()
        if not _is_legacy_static_cover_url(s):
            continue
        if not s.startswith("http"):
            # relative URL — need site origin; default to prod frontend
            base = os.environ.get("LEGACY_COVERS_BASE", "https://equipbible.com")
            s = f"{base.rstrip('/')}{s if s.startswith('/') else '/' + s}"

        print(f"Migrate course {cid[:8]}…  {iurl!r} → Storage")
        data, _ct, ext = _fetch_bytes(s)
        if len(data) > 5_242_880:
            print(f"  SKIP: file too large for bucket ({len(data)} B)", file=sys.stderr)
            continue
        new_url = upload_course_cover_bytes(
            settings.SUPABASE_URL,
            k,
            cid,
            data,
            ext=ext,
        )
        with eng.begin() as conn:
            conn.execute(
                text("UPDATE courses SET image_url = :u, updated_at = now() WHERE id = cast(:i AS uuid)"),
                {"u": new_url, "i": cid},
            )
        updated += 1

    print(f"Done. Updated {updated} course(s).")
    if updated:
        print("You can remove legacy files from ``frontend/public/`` (acts_*.png, public/covers/*).")


if __name__ == "__main__":
    main()
