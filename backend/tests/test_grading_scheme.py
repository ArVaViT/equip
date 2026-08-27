"""Unit tests for ``app.services.grading_scheme`` — Phase 1 / M1 of the
grading redesign (design doc: ``product/decisions/grading-system-redesign.md``,
accepted 2026-08-06).

What is worth pinning here, and why:

* **Course defaults.** Q1 answered ``letter`` at 70, and the whole "the
  backfill changes nothing" argument rests on new and existing courses landing
  on exactly the bands ``grade_calculator`` already applied. A default drifting
  to ``pass_fail`` would silently switch every course to a different pass rule.
* **The five-point ceiling.** ``pass_threshold > 75`` makes the «3» band
  unreachable — a course that no one can be «удовлетворительно» in. Guarded at
  three layers (DB CHECK, model CHECK, validator); the validator is tested
  here, the CHECK below.
* **Band validation.** Bands are admin-editable JSONB, which means a human
  types them. Non-monotonic, duplicated, or not-bottoming-at-0 tables are the
  three ways to make a score map to nothing or to two symbols.
* **Malformed bands degrade, never raise.** Grade display sits on the read path
  of nearly every teacher and student screen; a bad admin edit must not take
  those screens down.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.models.course import Course
from app.models.org_settings import DEFAULT_GRADE_BANDS, OrgSettings
from app.services.grading_scheme import (
    effective_bands,
    get_org_settings,
    score_passes,
    score_to_symbol,
    symbol_floor,
    validate_bands,
    validate_scheme_threshold,
)
from tests.conftest import TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# --------------------------------------------------------------------------
# org settings
# --------------------------------------------------------------------------


def test_get_org_settings_creates_the_row_with_shipped_defaults(db: Session) -> None:
    settings = get_org_settings(db, TEST_ORGANIZATION_ID)

    # Keyed by the organization since 2026-08-27. It used to be a boolean
    # primary key pinned to True — the idiom for "there can only be one" —
    # and that is exactly what stopped being true.
    assert settings.organization_id == TEST_ORGANIZATION_ID
    assert settings.default_grading_scheme == "letter"
    assert Decimal(str(settings.default_pass_threshold)) == Decimal("70")
    assert settings.grade_bands == DEFAULT_GRADE_BANDS


def test_two_organizations_do_not_share_a_grading_scale(db: Session) -> None:
    """The reason ``get_org_settings`` takes an organization at all.

    Until 2026-08-27 it read ``db.query(OrgSettings).first()`` — correct
    while one row existed by construction, and a silent wrong answer the
    moment a second organization has settings of its own. Not an error
    either: a plausible transcript, with somebody else's scale on it.
    """
    from app.models.organization import Organization

    other_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    db.add(Organization(id=other_id, slug="other-org", public_name="Other Organization"))
    db.flush()

    ours = get_org_settings(db, TEST_ORGANIZATION_ID)
    ours.default_grading_scheme = "five_point"
    theirs = get_org_settings(db, other_id)
    db.flush()

    assert theirs.organization_id == other_id
    assert theirs.default_grading_scheme == "letter", "one organization's scale reached another"
    assert get_org_settings(db, TEST_ORGANIZATION_ID).default_grading_scheme == "five_point"


def test_get_org_settings_is_idempotent(db: Session) -> None:
    """Second call must reuse this organization's row, not create a rival."""
    first = get_org_settings(db, TEST_ORGANIZATION_ID)
    first.city = "Indianapolis"
    db.flush()

    second = get_org_settings(db, TEST_ORGANIZATION_ID)

    assert second.city == "Indianapolis"
    assert db.query(OrgSettings).count() == 1


# --------------------------------------------------------------------------
# course defaults — the "backfill changes nothing" guarantee
# --------------------------------------------------------------------------


def test_new_course_inherits_letter_at_70(db: Session) -> None:
    course = Course(id="c-defaults", status="draft")
    db.add(course)
    db.flush()

    assert course.grading_scheme == "letter"
    assert Decimal(str(course.pass_threshold)) == Decimal("70")
    assert course.academic_hours is None


def test_letter_bands_match_what_the_calculator_already_applied(db: Session) -> None:
    """90/80/70/60 — the scale hardcoded in ``grade_calculator.LETTER_GRADES``.

    If these drift, the Q1 promise that existing courses keep grading exactly
    as before is broken.
    """
    bands = effective_bands(get_org_settings(db, TEST_ORGANIZATION_ID), "letter")

    assert [(str(f), s) for f, s in bands] == [
        ("90", "A"),
        ("80", "B"),
        ("70", "C"),
        ("60", "D"),
        ("0", "F"),
    ]


# --------------------------------------------------------------------------
# band resolution and symbol mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [(100, "A"), (90, "A"), (89.99, "B"), (80, "B"), (70, "C"), (60, "D"), (59.5, "F"), (0, "F")],
)
def test_score_to_symbol_letter_boundaries(db: Session, score: float, expected: str) -> None:
    bands = effective_bands(get_org_settings(db, TEST_ORGANIZATION_ID), "letter")
    assert score_to_symbol(score, "letter", bands) == expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [(95, "5"), (90, "5"), (89, "4"), (75, "4"), (74, "3"), (70, "3"), (69, "2"), (0, "2")],
)
def test_score_to_symbol_five_point_boundaries(db: Session, score: float, expected: str) -> None:
    bands = effective_bands(get_org_settings(db, TEST_ORGANIZATION_ID), "five_point")
    assert score_to_symbol(score, "five_point", bands) == expected


def test_schemes_without_bands_resolve_empty(db: Session) -> None:
    """``pass_fail`` and ``percent`` have no symbol table — by design.

    ``pass_fail`` is completion-native (D2): giving it bands would reintroduce
    the hidden average the design removed.
    """
    settings = get_org_settings(db, TEST_ORGANIZATION_ID)

    assert effective_bands(settings, "pass_fail") == []
    assert effective_bands(settings, "percent") == []
    assert score_to_symbol(88, "percent", []) is None


def test_malformed_admin_bands_fall_back_instead_of_raising(db: Session) -> None:
    settings = get_org_settings(db, TEST_ORGANIZATION_ID)
    settings.grade_bands = {"letter": [["not-a-number", "A"], [0, "F"]]}
    db.flush()

    bands = effective_bands(settings, "letter")

    assert [s for _, s in bands] == ["A", "B", "C", "D", "F"]


def test_empty_band_list_falls_back(db: Session) -> None:
    settings = get_org_settings(db, TEST_ORGANIZATION_ID)
    settings.grade_bands = {"five_point": []}
    db.flush()

    assert [s for _, s in effective_bands(settings, "five_point")] == ["5", "4", "3", "2"]


def test_admin_edited_bands_are_honoured(db: Session) -> None:
    """«5 от 85» — as common in UA practice as «5 от 90». The whole reason
    bands are data and not constants."""
    settings = get_org_settings(db, TEST_ORGANIZATION_ID)
    settings.grade_bands = {"five_point": [[85, "5"], [70, "4"], [60, "3"], [0, "2"]]}
    db.flush()

    bands = effective_bands(settings, "five_point")

    assert score_to_symbol(86, "five_point", bands) == "5"
    assert score_to_symbol(84, "five_point", bands) == "4"


def test_symbol_floor_backs_override_pass_determination(db: Session) -> None:
    """An override stores «B», not a number — pass is decided by the band floor (D7)."""
    bands = effective_bands(get_org_settings(db, TEST_ORGANIZATION_ID), "letter")

    assert symbol_floor("B", bands) == Decimal("80")
    assert symbol_floor("F", bands) == Decimal("0")
    assert symbol_floor("Z", bands) is None


# --------------------------------------------------------------------------
# pass determination
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "threshold", "passes"),
    [(70, 70, True), (69.99, 70, False), (100, 70, True), (0, 0, True)],
)
def test_score_passes_is_inclusive_at_the_line(score: float, threshold: float, passes: bool) -> None:
    assert score_passes(score, threshold) is passes


# --------------------------------------------------------------------------
# scheme + threshold validation (D8.1)
# --------------------------------------------------------------------------


def test_five_point_rejects_threshold_above_75() -> None:
    error = validate_scheme_threshold("five_point", Decimal("80"))

    assert error is not None
    assert "75" in error


def test_five_point_accepts_the_ceiling_itself() -> None:
    assert validate_scheme_threshold("five_point", Decimal("75")) is None


def test_letter_may_sit_above_the_five_point_ceiling() -> None:
    """The 75 cap is a five-point rule only; a strict letter course at 80 is legitimate."""
    assert validate_scheme_threshold("letter", Decimal("80")) is None


@pytest.mark.parametrize("threshold", [Decimal("-1"), Decimal("101")])
def test_threshold_must_be_a_percentage(threshold: Decimal) -> None:
    assert validate_scheme_threshold("letter", threshold) is not None


def test_unknown_scheme_is_rejected() -> None:
    assert validate_scheme_threshold("moodle_weighted", Decimal("70")) is not None


# --------------------------------------------------------------------------
# band validation (the admin write path)
# --------------------------------------------------------------------------


def test_valid_band_table_passes() -> None:
    assert validate_bands([[90, "A"], [80, "B"], [0, "F"]], "letter") is None


@pytest.mark.parametrize(
    ("bands", "fragment"),
    [
        ([[80, "B"], [90, "A"], [0, "F"]], "decreasing"),
        ([[90, "A"], [90, "B"], [0, "F"]], "decreasing"),
        ([[90, "A"], [80, "B"]], "lowest band"),
        ([[90, "A"], [80, "A"], [0, "F"]], "unique"),
        ([[110, "A"], [0, "F"]], "out of range"),
        ([[90, "A"], [0, "  "]], "must not be empty"),
        ("letters", "non-empty list"),
        ([], "non-empty list"),
        ([[90]], "[floor, symbol] pair"),
    ],
)
def test_invalid_band_tables_are_rejected(bands: object, fragment: str) -> None:
    error = validate_bands(bands, "letter")

    assert error is not None
    assert fragment in error


def test_five_point_three_floor_must_agree_with_the_pass_line() -> None:
    """Otherwise a student reads «3 (удовлетворительно)» while actually failing."""
    error = validate_bands(
        [[90, "5"], [75, "4"], [65, "3"], [0, "2"]],
        "five_point",
        pass_threshold=Decimal("70"),
    )

    assert error is not None
    assert "«3»" in error


def test_five_point_three_floor_matching_the_line_is_accepted() -> None:
    assert (
        validate_bands(
            [[90, "5"], [75, "4"], [70, "3"], [0, "2"]],
            "five_point",
            pass_threshold=Decimal("70"),
        )
        is None
    )
