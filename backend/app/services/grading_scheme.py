"""Grading schemes, band resolution and pass determination.

The single place that answers three questions the rest of the app keeps
asking: *what scheme is this course graded under*, *what symbol does a score
map to*, and *does that count as passing*.

Design: ``equipbible-docs/product/decisions/grading-system-redesign.md``
(Accepted 2026-08-06), decisions D1 and D3.

Why it exists
-------------
Before this module, ``grade_calculator.LETTER_GRADES`` hardcoded US letter
bands for every course on the platform, and the frontend kept its own copy of
the same scale in ``gradebook/types.ts``. Two copies of an institutional
policy, neither of which the institution could edit. Bands now live in
``org_settings.grade_bands`` (admin-editable), this module resolves them, and
the grading-config endpoint exports the effective set so the SPA renders from
the backend's answer instead of its own constants.

Teachers still get presets only — the anti-Moodle thesis holds at teacher
level. It is the *institution* that configures.
"""

from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.models.org_settings import DEFAULT_GRADE_BANDS, OrgSettings

GradingScheme = Literal["pass_fail", "percent", "five_point", "letter"]

SCHEMES: tuple[GradingScheme, ...] = ("pass_fail", "percent", "five_point", "letter")

#: Schemes whose result is a band symbol measured against ``pass_threshold``.
#: ``pass_fail`` is deliberately absent: its rule is completion-native (D2),
#: with no hidden average behind it.
BAND_SCHEMES: tuple[GradingScheme, ...] = ("five_point", "letter")

#: The five-point fail band reads «2 (неудовлетворительно)», never «незачёт» —
#: that word belongs to the зачёт system alone (minor #6 in the review).
FIVE_POINT_FAIL_CODE = "2"

#: Upper bound for a five-point pass line. Above 75 the «3» band would be
#: unreachable; mirrored as a CHECK on both ``courses`` and this module.
FIVE_POINT_MAX_THRESHOLD = Decimal("75")


def get_org_settings(db: Session) -> OrgSettings:
    """Return the single settings row, creating it with shipped defaults.

    The row is seeded by migration ``20260806140314``. The create-on-miss path
    covers a fresh test database (conftest builds from models, not migrations)
    and any environment that predates the seed, so callers never have to cope
    with ``None``.
    """
    settings = db.query(OrgSettings).first()
    if settings is None:
        settings = OrgSettings(
            id=True,
            default_grading_scheme="letter",
            default_pass_threshold=Decimal("70"),
            grade_bands=dict(DEFAULT_GRADE_BANDS),
        )
        db.add(settings)
        db.flush()
    return settings


def effective_bands(settings: OrgSettings, scheme: str) -> list[tuple[Decimal, str]]:
    """Resolve the band table for *scheme*, falling back to the shipped default.

    Returns ``(floor, symbol)`` pairs sorted high→low, ready for a first-match
    scan. Empty for schemes that have no bands (``pass_fail``, ``percent``).

    A malformed admin edit degrades to the shipped defaults rather than
    raising: grade display is on the read path of nearly every teacher and
    student screen, and a bad JSONB value must not take those screens down.
    Validation belongs on the write path, where the admin can see the error.
    """
    if scheme not in BAND_SCHEMES:
        return []
    raw = (settings.grade_bands or {}).get(scheme) or DEFAULT_GRADE_BANDS.get(scheme, [])
    bands: list[tuple[Decimal, str]] = []
    for entry in raw:
        try:
            floor, symbol = entry[0], str(entry[1])
            bands.append((Decimal(str(floor)), symbol))
        except (TypeError, ValueError, IndexError, ArithmeticError):
            return [(Decimal(str(f)), str(s)) for f, s in DEFAULT_GRADE_BANDS.get(scheme, [])]
    if not bands:
        return [(Decimal(str(f)), str(s)) for f, s in DEFAULT_GRADE_BANDS.get(scheme, [])]
    return sorted(bands, key=lambda b: b[0], reverse=True)


def score_to_symbol(score: float | Decimal, scheme: str, bands: list[tuple[Decimal, str]]) -> str | None:
    """Map a percentage to its band symbol («A», «4»), or ``None`` if the scheme has no bands."""
    if not bands:
        return None
    value = Decimal(str(score))
    for floor, symbol in bands:
        if value >= floor:
            return symbol
    return bands[-1][1]


def symbol_floor(symbol: str, bands: list[tuple[Decimal, str]]) -> Decimal | None:
    """Return the lower bound of the band *symbol* denotes.

    Used to decide whether a hand-set override passes: an override stores a
    code («B»), not a number, so pass determination measures the band's floor
    against ``pass_threshold`` (D7).
    """
    for floor, candidate in bands:
        if candidate == symbol:
            return floor
    return None


def score_passes(score: float | Decimal, pass_threshold: Decimal | float) -> bool:
    """Whether a computed percentage clears the course's result line."""
    return Decimal(str(score)) >= Decimal(str(pass_threshold))


def validate_scheme_threshold(scheme: str, pass_threshold: Decimal) -> str | None:
    """Validate a scheme+threshold pair; return an error message or ``None``.

    The pair is written through a single endpoint precisely so it can be
    revalidated as a unit (D8.1) — a scheme-only write must not be able to
    leave a course with an unreachable band.
    """
    if scheme not in SCHEMES:
        return f"Unknown grading scheme: {scheme!r}"
    if not (Decimal("0") <= pass_threshold <= Decimal("100")):
        return "pass_threshold must be between 0 and 100"
    if scheme == "five_point" and pass_threshold > FIVE_POINT_MAX_THRESHOLD:
        return "For the five-point scheme pass_threshold must be 75 or lower, otherwise the «3» band is unreachable"
    return None


def validate_bands(bands: object, scheme: str, pass_threshold: Decimal | None = None) -> str | None:
    """Validate an admin band edit; return an error message or ``None``.

    Enforces the three properties the display layer relies on: floors are
    numeric and within 0-100, they are strictly decreasing with no duplicates,
    and the table bottoms out at 0 so every score maps to some symbol. For
    five-point, the «3» floor must agree with the course pass line — otherwise
    a student could show «3 (удовлетворительно)» and still be failing.
    """
    if not isinstance(bands, list) or not bands:
        return "Bands must be a non-empty list of [floor, symbol] pairs"
    floors: list[Decimal] = []
    symbols: list[str] = []
    for entry in bands:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            return "Each band must be a [floor, symbol] pair"
        try:
            floor = Decimal(str(entry[0]))
        except ArithmeticError:
            return f"Band floor is not a number: {entry[0]!r}"
        if not (Decimal("0") <= floor <= Decimal("100")):
            return f"Band floor out of range 0-100: {floor}"
        symbol = str(entry[1]).strip()
        if not symbol:
            return "Band symbol must not be empty"
        floors.append(floor)
        symbols.append(symbol)

    if len(set(symbols)) != len(symbols):
        return "Band symbols must be unique"
    if floors != sorted(floors, reverse=True) or len(set(floors)) != len(floors):
        return "Band floors must be strictly decreasing"
    if floors[-1] != Decimal("0"):
        return "The lowest band must start at 0 so every score maps to a symbol"

    if scheme == "five_point" and pass_threshold is not None:
        three_floor = symbol_floor("3", [(f, s) for f, s in zip(floors, symbols, strict=True)])
        if three_floor is not None and three_floor != Decimal(str(pass_threshold)):
            return (
                f"The «3» band starts at {three_floor} but the pass threshold is "
                f"{pass_threshold} — a student would show «3 (удовлетворительно)» while failing"
            )
    return None
