# One-off: mint short-lived API JWT and POST the Pocket Glossary course to production.
# Run from ``backend/`` so ``.env`` loads:  python dev_run_pocket_glossary_production.py
# Uses JWT_SECRET from .env — must match Vercel env for the backend project.
# Cover: set ``GLOSSARY_COVER_FILE`` to a path *outside* this repo, then it uploads
# to Supabase ``course-assets`` (same as teacher UI). Do not commit course art in the project tree.

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import jwt
from sqlalchemy import create_engine, text

# Local imports after cwd
BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(str(BACKEND_DIR))
sys.path.insert(0, os.getcwd())

from app.core.config import settings  # noqa: E402
from app.core.course_cover_upload import upload_course_cover_bytes  # noqa: E402
from tests.glossary_pocket_payload import run_pocket_glossary  # noqa: E402

API_BASE = os.environ.get(
    "API_BASE",
    "https://api.equipbible.com/api/v1",
).rstrip("/")


def _request(method: str, path: str, token: str, body: object | None) -> dict:
    url = f"{API_BASE}{path}"
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} {method} {path}: {err[:2000]}", file=sys.stderr)
        raise SystemExit(1) from e


def _actor_id() -> uuid.UUID:
    """Who to mint the JWT for (becomes course ``created_by``).

    1) ``COURSE_OWNER_EMAIL`` if set (must be teacher or admin).
    2) Else first admin (typical project owner).
    3) Else first teacher. Never a blind ``LIMIT 1`` on teachers only.
    """
    eng = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    email = (os.environ.get("COURSE_OWNER_EMAIL") or "").strip().lower()
    with eng.connect() as conn:
        if email:
            row = conn.execute(
                text("SELECT id::text FROM profiles WHERE lower(email) = :e AND role IN ('teacher', 'admin') LIMIT 1"),
                {"e": email},
            ).fetchone()
            if not row:
                raise SystemExit(f"No teacher/admin profile for COURSE_OWNER_EMAIL={email!r}")
            return uuid.UUID(str(row[0]))
        row = conn.execute(
            text("SELECT id::text FROM profiles WHERE role = 'admin' ORDER BY created_at NULLS LAST LIMIT 1")
        ).fetchone()
        if row:
            return uuid.UUID(str(row[0]))
        row = conn.execute(text("SELECT id::text FROM profiles WHERE role = 'teacher' LIMIT 1")).fetchone()
    if not row:
        raise SystemExit("No teacher or admin in profiles — create one in the app first.")
    return uuid.UUID(str(row[0]))


def _mint_token(sub: uuid.UUID) -> str:
    now = int(time.time())
    payload = {
        "sub": str(sub),
        "aud": "authenticated",
        "exp": now + 3600,
        "iat": now,
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def _ext_from_name(name: str) -> str:
    base = (name or "").rsplit(".", 1)
    if len(base) < 2:
        return "png"
    e = base[-1].lower()
    if e not in ("png", "jpg", "jpeg", "webp", "gif"):
        return "png"
    if e == "jpeg":
        return "jpg"
    return e


def _resolve_cover_path() -> tuple[Path, str]:
    """Path to a cover on disk; must not live in the app repo (course data, not product code)."""
    env_p = (os.environ.get("GLOSSARY_COVER_FILE") or "").strip()
    if not env_p:
        raise SystemExit(
            "Set GLOSSARY_COVER_FILE to a PNG/JPEG path *outside* the repo, e.g. "
            "C:\\\\User\\\\Pictures\\\\glossary.png — course covers are not stored in the project tree."
        )
    p = Path(env_p).expanduser()
    if not p.is_file():
        raise SystemExit(f"GLOSSARY_COVER_FILE is not a file: {p}")
    return p, _ext_from_name(p.name)


def main() -> None:
    tid = _actor_id()
    token = _mint_token(tid)
    print(f"API_BASE={API_BASE}")
    print(f"Acting as user (JWT sub) {tid}")

    class _Http:
        def post(self, path: str, body: dict | None) -> dict:
            return _request("POST", path, token, body)

        def put(self, path: str, body: dict | None) -> dict:
            return _request("PUT", path, token, body)

    key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY (or legacy SUPABASE_KEY) must be set in .env to upload the cover.")

    cover_path, ext = _resolve_cover_path()
    data = cover_path.read_bytes()
    if len(data) > 5_242_880:
        raise SystemExit("Cover file exceeds course-assets bucket limit (5 MB).")

    def set_cover(course_id: str) -> str:
        return upload_course_cover_bytes(
            settings.SUPABASE_URL,
            key,
            course_id,
            data,
            ext=ext,
        )

    print(f"Cover file: {cover_path}  (uploads to course-assets/<course_id>/cover.{ext})")
    cid = run_pocket_glossary(_Http(), set_cover=set_cover)
    print("OK, course published:", cid)
    print(f"Open: https://equipbible.com (catalog) or teacher dashboard. Course id: {cid}")


if __name__ == "__main__":
    main()
