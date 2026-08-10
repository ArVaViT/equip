"""Closing and reopening a ведомость (D11 / M5).

A report is live; a document is not. Everything a sheet is computed from stays
editable after it is signed — a teacher can re-mark an essay, lift an exemption,
or hand-set a grade months later — so a printable rendered from live data would
change in the filing cabinet. Closing takes a snapshot and the printable reads
only from that.

Same reasoning as the certificate snapshot (M6), applied to the other signed
artifact. The two must age the same way, or a school ends up with a certificate
and a ведомость that disagree about the same student.

This is also where the pass rule finally gets used. ``score_passes`` and
``symbol_floor`` have existed in :mod:`app.services.grading_scheme` since the
scheme work landed and had no callers: nothing on the platform had yet needed
to answer "did this person pass", because the certificate gate is still only a
progress check. A signed document has to answer it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.ids import as_uuid
from app.models.content_version import ContentVersion
from app.models.enrollment import Enrollment
from app.models.grade_sheet import GradeSheet, GradeSheetRow
from app.models.user import User
from app.services.grade_calculator import calculate_all_student_grades
from app.services.grade_override import override_for_cohort
from app.services.grading_scheme import effective_bands, get_org_settings, score_passes, symbol_floor
from app.services.translation.resolve_for_display import fetch_course_titles_by_id

if TYPE_CHECKING:
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.models.course import Course
    from app.schemas.locale import LocaleCode

#: A result, not a computation state. The calculator's vocabulary answers "why
#: is there no number"; a signed document answers "what did this person get".
PASS = "pass"
FAIL = "fail"
COMPLETION_PASS = "completion_pass"
NOT_ATTESTED = "not_attested"


def _row_result(
    breakdown: Any,
    override_code: str | None,
    override_score: Decimal | None,
    *,
    scheme: str,
    pass_threshold: Decimal,
    bands: list[tuple[Decimal, str]],
) -> tuple[str, str | None, Decimal | None, bool]:
    """One student's line: ``(result_state, code, score, is_override)``.

    Order matters and is the design's, not a convenience:

    1. **A hand-set grade decides**, before anything else (D7). It comes first
       because of the case that made it necessary: a student excused from every
       item is "not attested", and the calculator's own comment says that is
       the one a teacher has to decide by hand — so the decision, once made,
       has to outrank the state that asked for it. A code is measured by its
       band's floor against the pass line, because an override stores a symbol
       and the line is a number.
    2. **"Not attested"** when nothing was assessed and nobody has decided.
       Neither a pass nor a failure; calling it either would put a verdict on a
       page where a person still has to make one.
    3. **Completion** for a course with nothing gradable in it — the shape most
       certificates here have come from.
    4. Otherwise the computed result against the pass line.
    """
    if override_code is not None:
        return (
            (PASS if _code_passes(override_code, scheme, pass_threshold, bands) else FAIL),
            override_code,
            None,
            True,
        )
    if override_score is not None:
        return (PASS if score_passes(override_score, pass_threshold) else FAIL), None, override_score, True

    if breakdown.result_state == "not_assessed":
        return NOT_ATTESTED, None, None, False
    if breakdown.result_state == "completion_pass":
        return COMPLETION_PASS, None, None, False
    if breakdown.result_state in {"not_graded_yet", "zero_weighted"}:
        # Nothing marked, or nothing that counts. There is no result to record,
        # and a document must not invent one.
        return NOT_ATTESTED, None, None, False

    passed = score_passes(breakdown.final_score, pass_threshold)
    return (
        (PASS if passed else FAIL),
        breakdown.letter_grade or None,
        None if breakdown.letter_grade else round(breakdown.final_score, 2),
        False,
    )


def _code_passes(code: str, scheme: str, pass_threshold: Decimal, bands: list) -> bool:
    """Whether a hand-set symbol clears the line.

    ``pass_fail`` has no bands by construction — its codes *are* the verdict
    (D2), so measuring «зачёт» against a numeric line found no floor and
    recorded a pass as a failure on the same printed row.
    """
    if scheme == "pass_fail":
        return code == "pass"
    floor = symbol_floor(code, bands)
    # A symbol outside this course's scale cannot be measured. It is left to
    # fail rather than guessed at, and `_refuse_reason` keeps it off a sheet.
    return floor is not None and score_passes(floor, pass_threshold)


#: Every ведомость closes in English, by decision. The value is stored rather
#: than assumed so that adding a language later costs nothing — without it, the
#: day a second language appears, every sheet already in the cabinet is of
#: unknown language and there is nothing to read it back from.
SHEET_LOCALE: LocaleCode = "en"


def _cohort_name(db: Session, cohort_id: UUID | None, locale: str) -> str | None:
    """The поток's name in the document's own language.

    The admin helper picks "whichever translation was entered first", which is
    fine for an admin list and wrong for a signed page: a school whose English
    name happened to be entered first would get it on a Russian ведомость.
    """
    if cohort_id is None:
        return None
    rows = (
        db.query(ContentVersion.locale, ContentVersion.text)
        .filter(
            ContentVersion.entity_type == "cohort",
            ContentVersion.entity_id == str(cohort_id),
            ContentVersion.field == "title",
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == "ok",
        )
        .all()
    )
    by_locale = {r.locale: r.text for r in rows}
    # The document's language first; any other translation is better than an
    # unnamed поток on a signed page, but only as a fallback.
    return by_locale.get(locale) or next(iter(by_locale.values()), None)


def refuse_reason(course: Course) -> str | None:
    """Why this course cannot be frozen yet, or ``None``.

    Only ``pass_fail``, and only because its rule is not built. «Зачёт» means
    every required piece of work accepted, not an average clearing a line (D2)
    — so the weighted percentage the calculator produces is not this course's
    result. Freezing it would put a verdict onto a signed page that the
    platform cannot justify, and a document is the last place to guess.

    Refusing is the honest answer until D2 lands. No production course uses the
    scheme, so this blocks nobody today; it is here so that the day one does,
    the ведомость says "not yet" instead of inventing a number.
    """
    if course.grading_scheme == "pass_fail":
        return (
            "«Зачёт/незачёт» is decided by whether every required piece of work was "
            "accepted, and that rule is not implemented yet. Closing a ведомость for "
            "this course would record a verdict the platform cannot justify."
        )
    return None


def active_sheet(db: Session, course_id: str, cohort_id: UUID | None) -> GradeSheet | None:
    """The sheet currently standing for this поток, if it has been closed."""
    return (
        db.query(GradeSheet)
        .filter(
            GradeSheet.course_id == course_id,
            GradeSheet.cohort_id == cohort_id if cohort_id else GradeSheet.cohort_id.is_(None),
            GradeSheet.superseded_at.is_(None),
        )
        .first()
    )


def students_in_scope(db: Session, course_id: str, cohort_id: UUID | None) -> list[str]:
    """Who belongs on this sheet.

    Cohort-scoped from the first day (D11): the moment a school runs the same
    course a second year, an unscoped sheet mixes two поток onto one signed
    page and nothing afterwards can tell them apart. ``cohort_id IS NULL`` is
    «без потока» — a real bucket for solo students, not "everyone".
    """
    query = (
        db.query(Enrollment.user_id)
        .join(User, User.id == Enrollment.user_id)
        .filter(Enrollment.course_id == course_id, User.deactivated_at.is_(None))
    )
    query = query.filter(Enrollment.cohort_id == cohort_id if cohort_id else Enrollment.cohort_id.is_(None))
    return [str(r.user_id) for r in query.all()]


def finalize_sheet(db: Session, course: Course, cohort_id: UUID | None, closed_by: UUID) -> GradeSheet:
    """Close the ведомость: freeze every student's official result.

    Re-closing supersedes the previous sheet rather than overwriting it, so the
    history of what was signed survives a correction.
    """
    previous = active_sheet(db, course.id, cohort_id)
    if previous is not None:
        from datetime import UTC, datetime

        previous.superseded_at = datetime.now(UTC)
        db.flush()

    settings = get_org_settings(db)
    scheme = course.grading_scheme or settings.default_grading_scheme
    bands = effective_bands(settings, scheme)

    sheet = GradeSheet(
        course_id=course.id,
        cohort_id=cohort_id,
        grading_scheme=scheme,
        pass_threshold=course.pass_threshold,
        finalized_by=closed_by,
        # The поток's name as it stood. Cohort names live in `content_versions`
        # and are editable; the heading on a signed page is not.
        locale=SHEET_LOCALE,
        cohort_name=_cohort_name(db, cohort_id, SHEET_LOCALE),
        course_title=fetch_course_titles_by_id(db, [course.id], display_locale=SHEET_LOCALE).get(course.id),
        # A document that changed after signature has to say so on its face,
        # and the document that says it must be the corrected one — not the
        # superseded page nobody will print again.
        corrects_sheet_id=previous.id if previous is not None and previous.reopened_at else None,
        correction_reason=previous.reopen_reason if previous is not None and previous.reopened_at else None,
    )
    db.add(sheet)
    db.flush()

    in_scope = set(students_in_scope(db, course.id, cohort_id))
    # One row per student, not per enrolment. `calculate_all_student_grades`
    # yields a row per enrolment, and a retake is deliberately a second
    # enrolment — so a returning student produced two lines with the same
    # primary key and the sheet could not be closed at all.
    seen: set[str] = set()
    for row in calculate_all_student_grades(db, course):
        if row["student_id"] not in in_scope or row["student_id"] in seen:
            continue
        seen.add(row["student_id"])
        # The calculator keys its results by string; the columns are UUIDs.
        # Coerced at the boundary — see `app.core.ids` for why this keeps
        # happening and why it is fixed here rather than inline.
        student_uuid = as_uuid(row["student_id"])
        if student_uuid is None:
            continue
        # Scoped to THIS sheet's поток. Asking "which is their current grade"
        # would stamp this year's mark onto last year's page.
        official = override_for_cohort(db, student_id=student_uuid, course_id=course.id, cohort_id=cohort_id)
        state, code, score, is_override = _row_result(
            row["breakdown"],
            official.override_code if official else None,
            official.override_score if official else None,
            scheme=scheme,
            pass_threshold=course.pass_threshold,
            bands=bands,
        )
        db.add(
            GradeSheetRow(
                sheet_id=sheet.id,
                student_id=student_uuid,
                # The name the document is signed under. Read live, a student
                # who marries rewrites a page already in the cabinet.
                student_name=row["student_name"] or row["student_email"],
                result_state=state,
                official_code=code,
                official_score=score,
                is_override=is_override,
            )
        )
    db.flush()
    return sheet


def reopen_sheet(db: Session, sheet: GradeSheet, reopened_by: UUID, reason: str) -> GradeSheet:
    """Reopen a closed sheet, on the record.

    A signed document cannot be quietly corrected. The reason is required by
    the table itself, and the sheet that replaces this one carries the mark
    forward — a document that changed after signature has to say so on its
    face, and the face people look at is the current one.

    Reopening twice is refused rather than allowed to overwrite the first
    reason: the earlier record is the part worth keeping.
    """
    from datetime import UTC, datetime

    if sheet.reopened_at is not None:
        raise ValueError("already reopened")
    sheet.reopened_at = datetime.now(UTC)
    sheet.reopened_by = reopened_by
    sheet.reopen_reason = reason
    db.flush()
    return sheet
