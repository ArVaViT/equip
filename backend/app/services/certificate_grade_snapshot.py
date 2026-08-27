"""The grade a certificate was issued on, frozen onto the certificate (M6).

A certificate is a document — printed, signed, kept for twenty years. Every
input it was computed from is live and editable: the course weights, the
school's grade bands, the pass line, the student's marks, whether a piece of
work was excused. Recompute it on read and the paper in the folder stops
matching the database the first time a director nudges the band table, silently
and retroactively, for everyone who ever graduated.

So the result is written once, at issuance, and never touched again. A later
edit to how the school grades is a decision about the future only — which is
what "grandfathering by construction" means in the design (Принцип 4).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.services.grade_calculator import calculate_student_grade_for_course
from app.services.grade_override import resolve_official_row
from app.services.grading_scheme import get_org_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.certificate import Certificate
    from app.models.course import Course

#: How the grade was decided. The question a director asks when two
#: certificates from the same course disagree.
VIA_COMPUTED = "computed"
VIA_OVERRIDE = "override"
VIA_COMPLETION = "completion"

#: States where no number was ever computed, so the result rests on completion.
_NO_NUMBER_STATES = {"completion_pass", "not_graded_yet", "zero_weighted", "not_assessed"}


def snapshot_certificate_grade(db: Session, cert: Certificate, course: Course | None) -> None:
    """Freeze the official grade onto *cert*. Called once, at admin approval.

    Deliberately silent when there is nothing to record: a certificate whose
    course has since been deleted keeps a NULL snapshot rather than a guess.
    NULL reads as "the platform did not record this", which is the truth for
    every certificate issued before this existed.
    """
    if course is None:
        return

    settings = get_org_settings(db, course.organization_id)
    cert.grading_scheme = course.grading_scheme or settings.default_grading_scheme
    cert.pass_threshold = course.pass_threshold

    # The override, when present, IS the official grade (D7) — it decides the
    # certificate, so it is what the certificate must carry.
    official_row = resolve_official_row(db, course_id=course.id, student_id=cert.user_id)
    if official_row is not None and official_row.override_code is not None:
        cert.official_code = official_row.override_code
        cert.official_score = None
        cert.graded_via = VIA_OVERRIDE
        return
    if official_row is not None and official_row.override_score is not None:
        cert.official_code = None
        cert.official_score = official_row.override_score
        cert.graded_via = VIA_OVERRIDE
        return

    breakdown = calculate_student_grade_for_course(db, course, cert.user_id)
    if breakdown.result_state in _NO_NUMBER_STATES:
        # No number was ever computed — the course had nothing gradable in it,
        # or nothing had been marked. Recording a 0 here would print a failure
        # onto a credential that was issued on completion, which is the shape
        # most of the certificates on this platform actually have.
        cert.official_code = None
        cert.official_score = None
        cert.graded_via = VIA_COMPLETION
        return

    cert.graded_via = VIA_COMPUTED
    # Percent courses have no symbol; the number is the result. Everything else
    # reads in symbols, and the symbol is what belongs on the paper.
    if cert.grading_scheme == "percent" or not breakdown.letter_grade:
        cert.official_code = None
        cert.official_score = Decimal(str(breakdown.final_score))
    else:
        cert.official_code = breakdown.letter_grade
        cert.official_score = None
