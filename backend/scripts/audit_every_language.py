"""Walk production as a reader of each language and report what they get.

Written after a week of shipping multilingual work that passed every
test and was still broken in production. The tests were mine and they
checked what I had assumed; nobody had opened the site in German. The
catalog answered 500 to every German visitor for days, the course page
served the whole tree in Russian, and outside the Daily Challenge there
was not a single German row in the database.

So this asks a different question from the test suite. Not "does the
resolver behave" but: fetch every reader-facing surface, four times,
once per language, and compare what actually comes back.

Three things it can tell you, and they are different problems:

* ``broken``  — the request failed. A reader of that language cannot
                use that page at all.
* ``foreign`` — text came back in a language the reader did not ask
                for. This is the failure that hides: the page renders,
                nothing errors, and only somebody who reads both
                languages notices.
* ``missing`` — the surface is empty here. Honest, and fixable by
                translating; it is what a backfill is for.

``foreign`` is judged by script and by the language detector, and the
detector refuses to guess between two languages of one alphabet — so
German prose sitting in a Ukrainian response is caught by its script,
while German in an English response needs the word evidence. Anything
it cannot name is reported as ``unknown`` rather than as a pass.

Use
---
  python -m scripts.audit_every_language                    # student's view
  python -m scripts.audit_every_language --verbose          # every sample

Needs ``SUPABASE_URL`` / ``SUPABASE_SECRET_KEY`` /
``SUPABASE_PUBLISHABLE_KEY`` to mint a session, and ``EQUIP_API`` to
point somewhere other than production.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.sanitize import html_to_plain_text
from app.schemas.locale import LOCALE_CODES
from app.services.language_detection import carries_language, detect_locale

API = os.getenv("EQUIP_API", "https://api.equipbible.com")
ACCOUNT = os.getenv("EQUIP_AUDIT_EMAIL", "arvavitcorp@gmail.com")

# Fields worth reading on each surface: the ones a person actually reads.
TEXT_KEYS = (
    "title",
    "description",
    "question_text",
    "option_text",
    "content",
    "text",
    "message",
    "explanation",
    "bible_book_label",
    "name",
)


@dataclass
class Finding:
    surface: str
    locale: str
    kind: str  # broken | foreign | missing | unknown
    detail: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0

    def add(self, surface: str, locale: str, kind: str, detail: str) -> None:
        self.findings.append(Finding(surface, locale, kind, detail))


def _session_token(client: httpx.Client) -> str:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    secret = os.environ["SUPABASE_SECRET_KEY"]
    publishable = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    link = client.post(
        f"{url}/auth/v1/admin/generate_link",
        headers={"Authorization": f"Bearer {secret}", "apikey": secret},
        json={"type": "magiclink", "email": ACCOUNT},
    ).json()
    otp = link.get("email_otp") or link.get("properties", {}).get("email_otp")
    verified = client.post(
        f"{url}/auth/v1/verify",
        headers={"apikey": publishable},
        json={"type": "magiclink", "email": ACCOUNT, "token": otp},
    ).json()
    return str(verified["access_token"])


def _texts(payload: Any, out: list[str]) -> None:
    """Every human-readable string in a response, however nested."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in TEXT_KEYS and isinstance(value, str) and value.strip():
                out.append(value)
            else:
                _texts(value, out)
    elif isinstance(payload, list):
        for item in payload:
            _texts(item, out)


def _inspect(report: Report, surface: str, locale: str, response: httpx.Response, *, verbose: bool) -> None:
    report.checked += 1
    if response.status_code >= 500:
        report.add(surface, locale, "broken", f"HTTP {response.status_code}")
        return
    if response.status_code >= 400:
        # 404 on an empty surface is ordinary; the caller decides which
        # surfaces must exist by listing them.
        return
    try:
        payload = response.json()
    except ValueError:
        return

    strings: list[str] = []
    _texts(payload, strings)
    if not strings:
        report.add(surface, locale, "missing", "no text at all")
        return

    for raw in strings:
        text = html_to_plain_text(raw)
        if not carries_language(text):
            continue
        detected = detect_locale(text)
        if detected is None:
            if verbose:
                report.add(surface, locale, "unknown", text[:90])
            continue
        if detected != locale:
            report.add(surface, locale, "foreign", f"reads as {detected}: {text[:80]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="report text the detector could not name")
    args = parser.parse_args()

    report = Report()
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        token = _session_token(client)
        auth = {"Authorization": f"Bearer {token}"}

        catalog = client.get(f"{API}/api/v1/courses", headers={**auth, "Accept-Language": "en"})
        course_ids = [c["id"] for c in catalog.json()] if catalog.status_code == 200 else []

        surfaces: list[tuple[str, str]] = [
            ("catalog", "/api/v1/courses"),
            ("daily challenge", "/api/v1/daily-challenge/today"),
            ("verse of the day", "/api/v1/verse-of-the-day"),
            ("my grades", "/api/v1/grades/my"),
            ("calendar", "/api/v1/calendar/events"),
        ]
        surfaces += [(f"course {cid[:8]}", f"/api/v1/courses/{cid}") for cid in course_ids]

        for locale in LOCALE_CODES:
            headers = {**auth, "Accept-Language": locale}
            for surface, path in surfaces:
                try:
                    response = client.get(f"{API}{path}", headers=headers)
                except httpx.HTTPError as exc:
                    report.add(surface, locale, "broken", str(exc))
                    continue
                _inspect(report, surface, locale, response, verbose=args.verbose)

    by_kind: dict[str, list[Finding]] = {}
    for finding in report.findings:
        by_kind.setdefault(finding.kind, []).append(finding)

    print(f"{report.checked} requests across {len(LOCALE_CODES)} languages\n")
    for kind in ("broken", "foreign", "missing", "unknown"):
        found = by_kind.get(kind, [])
        print(f"{kind:9} {len(found)}")
        seen: set[tuple[str, str]] = set()
        for finding in found:
            key = (finding.surface, finding.locale)
            if key in seen:
                continue
            seen.add(key)
            print(f"          [{finding.locale}] {finding.surface}: {finding.detail}")
    print()

    return 1 if by_kind.get("broken") or by_kind.get("foreign") else 0


if __name__ == "__main__":
    sys.exit(main())
