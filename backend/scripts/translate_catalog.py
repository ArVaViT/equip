#!/usr/bin/env python3
"""Draft the interface catalog for a new language.

Adding a language is five steps, and the sweep in
``services/translation/reconciler.py`` removed the one that did not
scale: existing courses now re-translate themselves. What is left that
a person still has to do is the interface — 2,000-odd keys in
``frontend/src/i18n/locales/<code>.json`` and the backend notification
catalog in ``app/core/i18n.py``.

Those are not course content and should not be treated as such. A
clumsy sentence in a lesson is a bad translation; a clumsy word on a
button is a bug, and one that every user meets on every visit. So this
script does not write them into the product — it produces a draft file
for a person to read, correct and commit.

What it handles that a bulk find-and-replace would not:

* **Placeholders.** ``{{count}}``, ``{{name}}``, ``%(email)s`` must
  survive exactly; a lost one is a crash or a literal "{{count}}" on
  screen. Each string is checked after translation and reported if the
  set changed.
* **Plural keys.** i18next's ``_one`` / ``_few`` / ``_many`` suffixes
  do not map between languages — Russian has three forms where English
  has two. Those keys are translated individually and flagged in the
  report, because the suffix set itself may need editing by hand.
* **Length.** Interface copy sits in fixed layouts. Anything that comes
  back much longer than its source is listed, so a person can look at
  it before a button breaks.

    python scripts/translate_catalog.py --locale fr --out /tmp/fr.json
    python scripts/translate_catalog.py --locale fr --backend --out /tmp/fr_backend.json

Reads ``GEMINI_API_KEY`` from the environment; run it under
``op run``. Writes a file and a report, and touches nothing else.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import urllib.request

REPO = Path(__file__).resolve().parents[2]
FRONTEND_LOCALES = REPO / "frontend" / "src" / "i18n" / "locales"

# Everything that must come back untouched.
PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}|%\([a-zA-Z_]+\)[sdifr]|%[sdifr]|<[^>]+>")

# i18next plural suffixes: the count of forms differs per language, so
# these are reported rather than assumed correct.
PLURAL_SUFFIX = re.compile(r"_(zero|one|two|few|many|other)$")

LANGUAGE_NAMES = {
    "ru": "Russian",
    "en": "English",
    "de": "German",
    "uk": "Ukrainian",
    "fr": "French",
    "es": "Spanish",
    "pl": "Polish",
    "ro": "Romanian",
    "pt": "Portuguese",
    "it": "Italian",
}

# Keys whose value is a name, not a sentence. Copied through untouched.
#
# Found the first time this script was run: "Equip" came back as
# "Équipement" — the product's own name, translated. A brand is not
# copy, and no amount of prompting makes that reliable, so the ones we
# know are pinned here.
DO_NOT_TRANSLATE = frozenset({"common.appName"})

SYSTEM = (
    "You are translating the user interface of Equip, a Bible-study platform, "
    "from {source} into {target}. This is interface copy: buttons, labels, "
    "short messages. Keep it short — it sits in a fixed layout. Preserve every "
    "placeholder ({{{{count}}}}, {{{{name}}}}, %(email)s) and every HTML tag "
    "exactly as given. Never translate the product name 'Equip' — it is a "
    "name, not a word. Use the vocabulary a church would use, not a "
    "corporation. Return only the translated string, with no quotes and no "
    "commentary."
)


def flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, path))
        elif isinstance(value, str):
            out[path] = value
    return out


def unflatten(flat: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path, value in flat.items():
        parts = path.split(".")
        cursor = out
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", required=True, help="target locale code, e.g. fr")
    parser.add_argument("--source", default="en", help="which existing catalog to translate from")
    parser.add_argument("--out", required=True, type=Path, help="where to write the draft")
    parser.add_argument("--backend", action="store_true", help="translate app/core/i18n.py's catalog instead")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="translate only the first N keys (a dry run)")
    args = parser.parse_args()

    target_name = LANGUAGE_NAMES.get(args.locale, args.locale)
    source_name = LANGUAGE_NAMES.get(args.source, args.source)

    if args.backend:
        from app.core.i18n import _CATALOG

        source_flat = dict(_CATALOG[args.source])  # type: ignore[index]
    else:
        source_path = FRONTEND_LOCALES / f"{args.source}.json"
        source_flat = flatten(json.loads(source_path.read_text(encoding="utf-8")))

    keys = list(source_flat)
    if args.limit:
        keys = keys[: args.limit]
    print(f"{len(keys)} keys, {args.source} → {args.locale}")

    # Called directly rather than through ``GeminiTranslationProvider``,
    # for two reasons. The provider refuses a locale that is not in
    # ``LOCALE_DISPLAY_NAMES`` yet — and this script is what you run
    # *before* the language exists in the code. And interface copy wants
    # its own instruction: short, fits a button, church vocabulary. The
    # course prompt is written for prose and scripture.
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    system = SYSTEM.format(source=source_name, target=target_name)

    def translate(key: str) -> tuple[str, str]:
        text = source_flat[key]
        if not text.strip() or key in DO_NOT_TRANSLATE:
            return key, text
        payload = json.dumps(
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": text}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 2048},
            }
        ).encode()
        request = urllib.request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "X-goog-api-key": api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode())
        except Exception as err:
            print(f"  ! {key}: {type(err).__name__}")
            return key, text
        candidate = (body.get("candidates") or [{}])[0]
        out = "".join(p.get("text", "") for p in (candidate.get("content", {}).get("parts") or []))
        return key, out.strip() or text

    translated: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (key, value) in enumerate(pool.map(translate, keys), start=1):
            translated[key] = value
            if i % 100 == 0:
                print(f"  {i}/{len(keys)}")

    # ── the report: what a person has to look at ──────────────────────
    lost_placeholders: list[str] = []
    plural_keys: list[str] = []
    much_longer: list[str] = []
    for key, value in translated.items():
        source = source_flat[key]
        if sorted(PLACEHOLDER.findall(source)) != sorted(PLACEHOLDER.findall(value)):
            lost_placeholders.append(key)
        if PLURAL_SUFFIX.search(key):
            plural_keys.append(key)
        if len(source) > 12 and len(value) > len(source) * 1.6:
            much_longer.append(key)

    payload = translated if args.backend else unflatten(translated)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwritten: {args.out}")

    print(f"\nplaceholders changed ({len(lost_placeholders)}) — these are bugs, fix before committing:")
    for key in lost_placeholders[:40]:
        print(f"  {key}: {source_flat[key]!r} → {translated[key]!r}")

    print(f"\nplural keys ({len(plural_keys)}) — the form set differs per language, check by hand:")
    for key in plural_keys[:40]:
        print(f"  {key}")

    renamed_product = [key for key, value in translated.items() if "Equip" in source_flat[key] and "Equip" not in value]
    print(f"\nproduct name translated ({len(renamed_product)}) — a brand is not copy:")
    for key in renamed_product[:20]:
        print(f"  {key}: {source_flat[key]!r} → {translated[key]!r}")

    print(f"\nmuch longer than the source ({len(much_longer)}) — may not fit the layout:")
    for key in much_longer[:40]:
        print(f"  {key}: {len(source_flat[key])} → {len(translated[key])} chars")

    print("\nThis is a draft. Read it before it ships — interface copy is the")
    print("one place a clumsy translation is a bug rather than a rough edge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
