"""One-shot: download + normalize public-domain Bible JSONs into the
flat dict shape the translation pipeline reads at runtime.

Source files:
  - https://raw.githubusercontent.com/bibleapi/bibleapi-bibles-json/master/kjv.json
    (KJV, 1769 — public domain in the US; resultset/row/field array-of-array shape)
  - https://raw.githubusercontent.com/bibleapi/bibleapi-bibles-json/master/rst.json
    (Russian Synodal, 1876 — public domain; NDJSON with book_id/chapter/verse/text)

Output: ``backend/app/services/bible/data/{kjv-en,synodal-ru}.json`` —
flat ``{"acts.1.8": "But ye shall receive power..."}`` dict, one per
locale. Compact (no whitespace) so the file is small enough for cold
starts.

Run from ``backend/`` after the raw files have been downloaded next to
the output dir (or with --download).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# 1-indexed book number (KJV / Protestant 66-book canon order) → canonical
# lowercase slug used in references like ``acts.1.8``. Synodal book_id (3-letter)
# is mapped via a parallel dict.
BOOK_NUM_TO_SLUG: dict[int, str] = {
    1: "genesis",
    2: "exodus",
    3: "leviticus",
    4: "numbers",
    5: "deuteronomy",
    6: "joshua",
    7: "judges",
    8: "ruth",
    9: "1samuel",
    10: "2samuel",
    11: "1kings",
    12: "2kings",
    13: "1chronicles",
    14: "2chronicles",
    15: "ezra",
    16: "nehemiah",
    17: "esther",
    18: "job",
    19: "psalms",
    20: "proverbs",
    21: "ecclesiastes",
    22: "songofsolomon",
    23: "isaiah",
    24: "jeremiah",
    25: "lamentations",
    26: "ezekiel",
    27: "daniel",
    28: "hosea",
    29: "joel",
    30: "amos",
    31: "obadiah",
    32: "jonah",
    33: "micah",
    34: "nahum",
    35: "habakkuk",
    36: "zephaniah",
    37: "haggai",
    38: "zechariah",
    39: "malachi",
    40: "matthew",
    41: "mark",
    42: "luke",
    43: "john",
    44: "acts",
    45: "romans",
    46: "1corinthians",
    47: "2corinthians",
    48: "galatians",
    49: "ephesians",
    50: "philippians",
    51: "colossians",
    52: "1thessalonians",
    53: "2thessalonians",
    54: "1timothy",
    55: "2timothy",
    56: "titus",
    57: "philemon",
    58: "hebrews",
    59: "james",
    60: "1peter",
    61: "2peter",
    62: "1john",
    63: "2john",
    64: "3john",
    65: "jude",
    66: "revelation",
}

# Synodal source uses 3-letter ``book_id`` strings. Keep this in sync with
# BOOK_NUM_TO_SLUG (same canon, same names).
SYNODAL_BOOK_ID_TO_SLUG: dict[str, str] = {
    "Gen": "genesis",
    "Exod": "exodus",
    "Lev": "leviticus",
    "Num": "numbers",
    "Deut": "deuteronomy",
    "Josh": "joshua",
    "Judg": "judges",
    "Ruth": "ruth",
    "1Sam": "1samuel",
    "2Sam": "2samuel",
    "1Kgs": "1kings",
    "2Kgs": "2kings",
    "1Chr": "1chronicles",
    "2Chr": "2chronicles",
    "Ezra": "ezra",
    "Neh": "nehemiah",
    "Esth": "esther",
    "Job": "job",
    "Ps": "psalms",
    "Prov": "proverbs",
    "Eccl": "ecclesiastes",
    "Song": "songofsolomon",
    "Isa": "isaiah",
    "Jer": "jeremiah",
    "Lam": "lamentations",
    "Ezek": "ezekiel",
    "Dan": "daniel",
    "Hos": "hosea",
    "Joel": "joel",
    "Amos": "amos",
    "Obad": "obadiah",
    "Jonah": "jonah",
    "Mic": "micah",
    "Nah": "nahum",
    "Hab": "habakkuk",
    "Zeph": "zephaniah",
    "Hag": "haggai",
    "Zech": "zechariah",
    "Mal": "malachi",
    "Matt": "matthew",
    "Mark": "mark",
    "Luke": "luke",
    "John": "john",
    "Acts": "acts",
    "Rom": "romans",
    "1Cor": "1corinthians",
    "2Cor": "2corinthians",
    "Gal": "galatians",
    "Eph": "ephesians",
    "Phil": "philippians",
    "Col": "colossians",
    "1Thess": "1thessalonians",
    "2Thess": "2thessalonians",
    "1Tim": "1timothy",
    "2Tim": "2timothy",
    "Titus": "titus",
    "Phlm": "philemon",
    "Heb": "hebrews",
    "Jas": "james",
    "1Pet": "1peter",
    "2Pet": "2peter",
    "1John": "1john",
    "2John": "2john",
    "3John": "3john",
    "Jude": "jude",
    "Rev": "revelation",
}


def _key(slug: str, chapter: int | str, verse: int | str) -> str:
    return f"{slug}.{int(chapter)}.{int(verse)}"


def normalize_kjv(raw_path: Path) -> dict[str, str]:
    """KJV uses ``{"resultset":{"row":[{"field":[verse_id, book_num, chapter, verse, text]}]}}``."""
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in raw["resultset"]["row"]:
        _verse_id, book_num, chapter, verse, text = row["field"]
        slug = BOOK_NUM_TO_SLUG.get(int(book_num))
        if slug is None:
            continue
        out[_key(slug, chapter, verse)] = text
    return out


def normalize_synodal(raw_path: Path) -> dict[str, str]:
    """RST source is NDJSON: one ``{book_id, chapter, verse, text, ...}`` object per line."""
    out: dict[str, str] = {}
    with raw_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            slug = SYNODAL_BOOK_ID_TO_SLUG.get(row["book_id"])
            if slug is None:
                # Skip deuterocanonicals or unknown books.
                continue
            out[_key(slug, row["chapter"], row["verse"])] = row["text"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "app" / "services" / "bible" / "data",
    )
    parser.add_argument("--download", action="store_true", help="re-download raw JSON before normalizing")
    parser.add_argument("--keep-raw", action="store_true", help="don't delete the raw download files after normalizing")
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    kjv_raw = data_dir / "kjv-raw.json"
    synodal_raw = data_dir / "synodal-raw.json"

    if args.download or not kjv_raw.exists():
        print(f"Downloading KJV → {kjv_raw}")
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/bibleapi/bibleapi-bibles-json/master/kjv.json",
            kjv_raw,
        )
    if args.download or not synodal_raw.exists():
        print(f"Downloading Synodal → {synodal_raw}")
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/bibleapi/bibleapi-bibles-json/master/rst.json",
            synodal_raw,
        )

    print("Normalizing KJV…")
    kjv_data = normalize_kjv(kjv_raw)
    print(f"  {len(kjv_data):,} verses")

    print("Normalizing Synodal…")
    synodal_data = normalize_synodal(synodal_raw)
    print(f"  {len(synodal_data):,} verses")

    kjv_out = data_dir / "kjv-en.json"
    synodal_out = data_dir / "synodal-ru.json"
    kjv_out.write_text(json.dumps(kjv_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    synodal_out.write_text(
        json.dumps(synodal_data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"Wrote {kjv_out} ({kjv_out.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"Wrote {synodal_out} ({synodal_out.stat().st_size / 1024 / 1024:.2f} MB)")

    if not args.keep_raw:
        kjv_raw.unlink(missing_ok=True)
        synodal_raw.unlink(missing_ok=True)
        print("Cleaned up raw files (use --keep-raw to retain)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
