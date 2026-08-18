#!/usr/bin/env python3
"""Does production run on the settings this repository describes?

Written after finding out that it did not. `GEMINI_MODEL` was corrected
in `app/core/config.py` in May and production kept running the old
value for 81 days, because a Vercel environment variable overrides the
default and nothing ever compared the two. The cost was roughly 840
billed-but-unread tokens per translated string and six times the
latency, and the only reason it surfaced at all is that somebody asked.

This is that comparison, as a command:

    cd backend
    vercel env pull --environment=production /tmp/prod.env
    python scripts/audit_prod_settings.py /tmp/prod.env

It prints every setting where production disagrees with the default,
and flags two specific hazards:

* **A value the audit cannot read.** Vercel marks new variables
  "sensitive" by default, and a sensitive variable comes back as
  `[SENSITIVE]` — invisible to `vercel env pull`, to the dashboard, and
  to this script. That is right for a key and wrong for a feature flag:
  a setting nobody can read is a setting nobody can check. Store flags
  and model names with `--no-sensitive`.
* **An unmeasured model.** `MEASURED_GEMINI_MODELS` lists what has
  actually been benchmarked for cost, speed and quality. Running
  something else is allowed and should be deliberate.

Secrets are never printed — only whether they are set.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import MEASURED_GEMINI_MODELS, Settings

SECRET_HINTS = ("KEY", "SECRET", "PASSWORD", "TOKEN", "DSN", "DATABASE_URL")


def load_env(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"')
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    env = load_env(pathlib.Path(sys.argv[1]))

    findings: list[str] = []
    differences: list[tuple[str, str, str]] = []

    for name, field in Settings.model_fields.items():
        if name not in env:
            continue
        actual = env[name]
        secret = any(hint in name for hint in SECRET_HINTS)

        if actual == "[SENSITIVE]" and not secret:
            findings.append(
                f"{name} is stored as sensitive, so nothing can read it back — "
                f"not this audit, not the dashboard, not you. Re-add it with "
                f"`vercel env add {name} production --no-sensitive --force`."
            )
            continue

        default = field.default
        if default is None or repr(default) == "PydanticUndefined":
            continue
        same = str(default) == actual or (
            isinstance(default, bool) and actual.lower() == str(default).lower()
        )
        if not same:
            differences.append(
                (
                    name,
                    "<secret>" if secret else repr(default),
                    "<set>" if secret else repr(actual),
                )
            )

    model = env.get("GEMINI_MODEL")
    if model and model not in MEASURED_GEMINI_MODELS:
        findings.append(
            f"GEMINI_MODEL is {model!r}, which is not in MEASURED_GEMINI_MODELS "
            f"({', '.join(sorted(MEASURED_GEMINI_MODELS))}). Its cost, speed and "
            f"translation quality are unverified — measure before trusting it."
        )

    if differences:
        print("Production differs from the defaults in this repository:\n")
        print(f"  {'setting':38} {'default':30} production")
        print("  " + "-" * 84)
        for name, default, actual in differences:
            print(f"  {name:38} {default:30} {actual}")
        print("\n(Differing is normal — production is where the real values live.")
        print("What matters is that every difference is one somebody chose.)\n")
    else:
        print("Production matches every default in this repository.\n")

    if findings:
        print("Worth acting on:\n")
        for finding in findings:
            print(f"  * {finding}\n")
        return 1

    print("No hazards found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
