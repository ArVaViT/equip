"""Build the full-year Daily Challenge passage manifest.

Emits `scripts/data/daily_challenge_seed_passages_full.json` — ~220 curated
passages spread across the canon and balanced over the three question
categories, enough to schedule one unique passage per day from 2026-06-17
through the end of 2026 (with buffer for editorial-gate rejections).

Selection rules (so the generator has the best shot at a clean,
unambiguous question):
  - narrative_recall  -> narrative chapters ("what happened")
  - passage_exegesis  -> teaching passages ("what it means")
  - cross_reference   -> passages with a well-known OT<->NT or
                         prophecy/fulfilment link
Chapter-level refs (no verse range) are used wherever a whole-chapter
context is natural; that also avoids emitting an invalid verse range.

Run:  python -m scripts.build_full_dc_manifest
"""

from __future__ import annotations

import json
from pathlib import Path

N, E, C = "narrative_recall", "passage_exegesis", "cross_reference"

# (book, chapter, category) or (book, chapter, verse_from, verse_to, category)
_RAW: list[tuple] = [
    # ---- Genesis / Pentateuch (narrative + foundational) ----
    ("Genesis", 1, E),
    ("Genesis", 2, N),
    ("Genesis", 3, N),
    ("Genesis", 6, N),
    ("Genesis", 7, N),
    ("Genesis", 9, C),
    ("Genesis", 12, C),
    ("Genesis", 15, C),
    ("Genesis", 22, C),
    ("Genesis", 28, N),
    ("Genesis", 37, N),
    ("Genesis", 39, N),
    ("Genesis", 41, N),
    ("Genesis", 45, N),
    ("Genesis", 50, E),
    ("Exodus", 3, N),
    ("Exodus", 12, C),
    ("Exodus", 14, N),
    ("Exodus", 16, N),
    ("Exodus", 20, E),
    ("Exodus", 32, N),
    ("Exodus", 34, E),
    ("Leviticus", 16, C),
    ("Leviticus", 19, E),
    ("Leviticus", 23, E),
    ("Numbers", 13, N),
    ("Numbers", 14, N),
    ("Numbers", 21, C),
    ("Deuteronomy", 6, E),
    ("Deuteronomy", 8, E),
    ("Deuteronomy", 30, E),
    ("Deuteronomy", 34, N),
    # ---- History ----
    ("Joshua", 1, E),
    ("Joshua", 6, N),
    ("Joshua", 24, N),
    ("Judges", 6, N),
    ("Judges", 7, N),
    ("Judges", 16, N),
    ("Ruth", 1, N),
    ("Ruth", 4, C),
    ("1 Samuel", 3, N),
    ("1 Samuel", 16, N),
    ("1 Samuel", 17, N),
    ("2 Samuel", 7, C),
    ("2 Samuel", 11, N),
    ("2 Samuel", 12, N),
    ("1 Kings", 3, N),
    ("1 Kings", 18, N),
    ("1 Kings", 19, N),
    ("2 Kings", 5, N),
    ("2 Kings", 2, N),
    ("Nehemiah", 8, N),
    ("Esther", 4, N),
    ("Esther", 7, N),
    # ---- Wisdom / Psalms (exegesis-heavy) ----
    ("Job", 1, N),
    ("Job", 38, E),
    ("Job", 42, N),
    ("Psalms", 1, E),
    ("Psalms", 8, E),
    ("Psalms", 19, E),
    ("Psalms", 22, C),
    ("Psalms", 23, E),
    ("Psalms", 51, E),
    ("Psalms", 91, E),
    ("Psalms", 103, E),
    ("Psalms", 110, C),
    ("Psalms", 119, 1, 16, E),
    ("Psalms", 121, E),
    ("Psalms", 139, E),
    ("Proverbs", 3, E),
    ("Proverbs", 31, E),
    ("Ecclesiastes", 3, E),
    ("Ecclesiastes", 12, E),
    ("Song of Solomon", 2, E),
    # ---- Prophets (cross-reference heavy) ----
    ("Isaiah", 6, N),
    ("Isaiah", 7, C),
    ("Isaiah", 9, C),
    ("Isaiah", 40, E),
    ("Isaiah", 53, C),
    ("Isaiah", 55, E),
    ("Isaiah", 61, C),
    ("Jeremiah", 1, N),
    ("Jeremiah", 29, E),
    ("Jeremiah", 31, C),
    ("Ezekiel", 36, C),
    ("Ezekiel", 37, C),
    ("Daniel", 2, N),
    ("Daniel", 3, N),
    ("Daniel", 6, N),
    ("Daniel", 9, C),
    ("Hosea", 11, C),
    ("Joel", 2, C),
    ("Amos", 5, E),
    ("Jonah", 1, N),
    ("Jonah", 2, N),
    ("Jonah", 3, N),
    ("Micah", 5, C),
    ("Micah", 6, E),
    ("Habakkuk", 2, C),
    ("Zechariah", 9, C),
    ("Malachi", 3, C),
    # ---- Matthew ----
    ("Matthew", 1, C),
    ("Matthew", 2, C),
    ("Matthew", 3, N),
    ("Matthew", 4, N),
    ("Matthew", 5, E),
    ("Matthew", 6, E),
    ("Matthew", 7, E),
    ("Matthew", 13, E),
    ("Matthew", 16, N),
    ("Matthew", 17, N),
    ("Matthew", 18, E),
    ("Matthew", 22, E),
    ("Matthew", 24, E),
    ("Matthew", 26, N),
    ("Matthew", 27, N),
    ("Matthew", 28, N),
    # ---- Mark ----
    ("Mark", 1, N),
    ("Mark", 2, N),
    ("Mark", 4, E),
    ("Mark", 5, N),
    ("Mark", 8, N),
    ("Mark", 10, E),
    ("Mark", 12, E),
    ("Mark", 15, N),
    ("Mark", 16, N),
    # ---- Luke ----
    ("Luke", 1, N),
    ("Luke", 2, N),
    ("Luke", 4, N),
    ("Luke", 10, E),
    ("Luke", 15, E),
    ("Luke", 18, E),
    ("Luke", 19, N),
    ("Luke", 22, N),
    ("Luke", 23, N),
    ("Luke", 24, N),
    # ---- John ----
    ("John", 1, C),
    ("John", 3, E),
    ("John", 4, N),
    ("John", 6, E),
    ("John", 8, E),
    ("John", 10, E),
    ("John", 11, N),
    ("John", 13, N),
    ("John", 14, E),
    ("John", 15, E),
    ("John", 17, E),
    ("John", 19, N),
    ("John", 20, N),
    ("John", 21, N),
    # ---- Acts ----
    ("Acts", 1, N),
    ("Acts", 2, C),
    ("Acts", 3, N),
    ("Acts", 4, N),
    ("Acts", 7, N),
    ("Acts", 8, N),
    ("Acts", 9, N),
    ("Acts", 10, N),
    ("Acts", 12, N),
    ("Acts", 16, N),
    ("Acts", 17, N),
    ("Acts", 20, E),
    ("Acts", 27, N),
    # ---- Romans ----
    ("Romans", 1, E),
    ("Romans", 3, E),
    ("Romans", 5, E),
    ("Romans", 6, E),
    ("Romans", 8, E),
    ("Romans", 10, C),
    ("Romans", 12, E),
    # ---- Corinthians ----
    ("1 Corinthians", 1, E),
    ("1 Corinthians", 12, E),
    ("1 Corinthians", 13, E),
    ("1 Corinthians", 15, E),
    ("2 Corinthians", 5, E),
    ("2 Corinthians", 12, N),
    # ---- Paul's letters ----
    ("Galatians", 2, E),
    ("Galatians", 5, E),
    ("Ephesians", 1, E),
    ("Ephesians", 2, E),
    ("Ephesians", 4, E),
    ("Ephesians", 6, E),
    ("Philippians", 2, E),
    ("Philippians", 4, E),
    ("Colossians", 1, E),
    ("Colossians", 3, E),
    ("1 Thessalonians", 4, E),
    ("2 Thessalonians", 2, E),
    ("1 Timothy", 3, E),
    ("2 Timothy", 3, E),
    ("Titus", 2, E),
    ("Philemon", 1, N),
    # ---- General epistles ----
    ("Hebrews", 1, C),
    ("Hebrews", 4, E),
    ("Hebrews", 11, E),
    ("Hebrews", 12, E),
    ("James", 1, E),
    ("James", 2, E),
    ("1 Peter", 1, E),
    ("1 Peter", 2, C),
    ("2 Peter", 1, E),
    ("1 John", 1, E),
    ("1 John", 3, E),
    ("1 John", 4, E),
    ("Jude", 1, E),
    # ---- Revelation ----
    ("Revelation", 1, N),
    ("Revelation", 3, E),
    ("Revelation", 5, C),
    ("Revelation", 21, C),
    ("Revelation", 22, C),
]


def _entry(t: tuple) -> dict:
    if len(t) == 3:
        book, chapter, category = t
        return {"book": book, "chapter": chapter, "category": category}
    book, chapter, vf, vt, category = t
    return {"book": book, "chapter": chapter, "verse_from": vf, "verse_to": vt, "category": category}


def main() -> None:
    passages = [_entry(t) for t in _RAW]
    # Guard against accidental duplicates (same book+chapter+verse window).
    seen = set()
    dupes = []
    for p in passages:
        key = (p["book"], p["chapter"], p.get("verse_from"), p.get("verse_to"))
        if key in seen:
            dupes.append(key)
        seen.add(key)
    counts = {N: 0, E: 0, C: 0}
    for p in passages:
        counts[p["category"]] += 1
    out = Path(__file__).parent / "data" / "daily_challenge_seed_passages_full.json"
    out.write_text(json.dumps({"passages": passages}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(passages)} passages -> {out}")
    print(f"categories: {counts}")
    if dupes:
        print(f"WARNING duplicates: {dupes}")


if __name__ == "__main__":
    main()
