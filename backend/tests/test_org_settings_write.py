"""The school can finally set its own name, scale and pass line (D1).

Every one of these values has been read-only since it was introduced. Putting a
partner school's name on their own ведомость meant somebody opening the
production database and running an UPDATE.

The band table is the dangerous one: it is shared, so editing it re-labels
every live grade on the platform at once — the same 84% that read «B» yesterday
reads «A» today. That is what a school changing its own scale means. What must
not happen is a document moving, and the last two tests here are about exactly
that.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.audit_log import AuditLog
from app.models.certificate import Certificate, CertificateStatus
from app.models.course import Course
from app.models.grade_sheet import GradeSheet, GradeSheetRow
from app.models.org_settings import DEFAULT_GRADE_BANDS
from app.services.grading_scheme import get_org_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

URL = "/api/v1/admin/org-settings"

UA_LETTERS = [[85, "A"], [75, "B"], [65, "C"], [60, "D"], [0, "F"]]


def test_an_admin_can_put_the_school_on_its_own_documents(admin_client, db: Session) -> None:
    """The name printed on every ведомость. Onboarding a school used to mean an
    UPDATE run by hand against production."""
    response = admin_client.put(
        URL,
        json={"school_name_ru": "Библейская школа «Слово»", "school_name_en": "Word Bible School", "city": "Kyiv"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["school_name_en"] == "Word Bible School"
    assert get_org_settings(db).city == "Kyiv"


def test_a_school_can_set_its_own_scale(admin_client, db: Session) -> None:
    """«5 от 85» is as common in Ukrainian practice as «5 от 90». Hardcoding
    the boundaries would make every onboarded school a code change."""
    response = admin_client.put(URL, json={"grade_bands": {"letter": UA_LETTERS}})

    assert response.status_code == 200, response.text
    assert response.json()["grade_bands"]["letter"] == UA_LETTERS


def test_leaving_a_field_out_leaves_it_alone(admin_client, db: Session) -> None:
    """A director fixing a typo in the city must not have to resend the band
    table — and a request that omitted it must not wipe the school's scale."""
    admin_client.put(URL, json={"grade_bands": {"letter": UA_LETTERS}})

    admin_client.put(URL, json={"city": "Lviv"})

    settings = get_org_settings(db)
    assert settings.city == "Lviv"
    assert settings.grade_bands["letter"] == UA_LETTERS


def test_an_empty_request_is_refused_rather_than_recorded(admin_client, db: Session) -> None:
    """Otherwise the audit log fills with entries that changed nothing, and the
    one entry that matters gets read past."""
    assert admin_client.put(URL, json={}).status_code == 400


# ---------------------------------------------------------------------------
# The validator that had no callers
# ---------------------------------------------------------------------------


def test_a_gap_in_the_scale_is_refused(admin_client, db: Session) -> None:
    """Bands must bottom out at 0 or some scores map to no symbol at all —
    which is a student with a grade the platform cannot name."""
    response = admin_client.put(URL, json={"grade_bands": {"letter": [[90, "A"], [80, "B"]]}})

    assert response.status_code == 422
    assert "0" in response.json()["detail"]["message"]


def test_a_scale_that_climbs_is_refused(admin_client, db: Session) -> None:
    response = admin_client.put(URL, json={"grade_bands": {"letter": [[70, "A"], [90, "B"], [0, "F"]]}})

    assert response.status_code == 422
    assert "decreasing" in response.json()["detail"]["message"]


def test_a_three_that_would_be_shown_to_a_failing_student_is_refused(admin_client, db: Session) -> None:
    """«3 (удовлетворительно)» on the screen of somebody who has not passed is
    the specific lie this check exists to prevent."""
    response = admin_client.put(
        URL,
        json={
            "default_grading_scheme": "five_point",
            "default_pass_threshold": 70,
            "grade_bands": {"five_point": [[90, "5"], [75, "4"], [60, "3"], [0, "2"]]},
        },
    )

    assert response.status_code == 422
    assert "3" in response.json()["detail"]["message"]


def test_the_three_is_checked_against_the_line_being_written_not_the_old_one(admin_client, db: Session) -> None:
    """Both change in one request. Checking the new table against the previous
    threshold accepts a pair that is wrong the moment it lands."""
    response = admin_client.put(
        URL,
        json={
            "default_grading_scheme": "five_point",
            "default_pass_threshold": 65,
            "grade_bands": {"five_point": [[90, "5"], [75, "4"], [65, "3"], [0, "2"]]},
        },
    )

    assert response.status_code == 200, response.text


def test_a_five_point_school_cannot_set_an_unreachable_pass_line(admin_client, db: Session) -> None:
    response = admin_client.put(URL, json={"default_grading_scheme": "five_point", "default_pass_threshold": 80})

    assert response.status_code == 422
    assert "75" in response.json()["detail"]["message"]


def test_bands_for_a_scheme_that_has_none_are_refused(admin_client, db: Session) -> None:
    """`pass_fail` is decided by acceptance, not by a number (D2), and `percent`
    shows the number itself. A band table there would be config that nothing
    reads — and somebody would edit it expecting an effect."""
    response = admin_client.put(URL, json={"grade_bands": {"pass_fail": [[50, "зачёт"], [0, "незачёт"]]}})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Who may, and what it leaves behind
# ---------------------------------------------------------------------------


def test_a_teacher_cannot_change_the_school(client, db: Session, teacher) -> None:
    """Bands are institutional (D1): one teacher moving the boundary would move
    every other teacher's grades with it."""
    assert client.put(URL, json={"city": "Kyiv"}).status_code == 403


def test_a_student_cannot_read_it(student_client, db: Session, student) -> None:
    assert student_client.get(URL).status_code == 403


def test_the_previous_scale_is_kept_in_full(admin_client, db: Session) -> None:
    """Six months on, "who changed the scale and what was it before" is the only
    question this row is ever asked. A diff saying «grade_bands: changed» does
    not answer it."""
    admin_client.put(URL, json={"grade_bands": {"letter": UA_LETTERS}})

    entry = db.query(AuditLog).filter(AuditLog.action == "org_settings_updated").one()

    assert entry.details["changed"] == ["grade_bands"]
    assert entry.details["previous"]["grade_bands"]["letter"] == DEFAULT_GRADE_BANDS["letter"]
    assert entry.details["current"]["grade_bands"]["letter"] == UA_LETTERS


# ---------------------------------------------------------------------------
# Documents do not move
# ---------------------------------------------------------------------------


def _course(db: Session, course_id: str) -> None:
    db.add(Course(id=course_id, status="published", created_by=TEACHER_ID, grading_scheme="letter"))
    db.flush()


def test_a_closed_sheet_keeps_the_grades_it_was_signed_with(admin_client, db: Session, teacher) -> None:
    """A ведомость renders from its snapshot. If a band edit could reach into a
    signed document, the signature would mean nothing (D11)."""
    _course(db, "c-sheet")
    sheet = GradeSheet(
        id=uuid.uuid4(),
        course_id="c-sheet",
        locale="en",
        grading_scheme="letter",
        pass_threshold=Decimal("70"),
        finalized_at=datetime.now(UTC),
        finalized_by=TEACHER_ID,
    )
    db.add(sheet)
    db.flush()
    db.add(
        GradeSheetRow(
            sheet_id=sheet.id,
            student_id=STUDENT_ID,
            student_name="Пётр Иванов",
            result_state="pass",
            official_code="B",
        )
    )
    db.commit()

    admin_client.put(URL, json={"grade_bands": {"letter": UA_LETTERS}})

    row = db.query(GradeSheetRow).filter(GradeSheetRow.sheet_id == sheet.id).one()
    db.refresh(row)
    assert row.official_code == "B", "the signed line still says what it said"


def test_an_issued_certificate_keeps_its_grade(admin_client, db: Session) -> None:
    """Grandfathering by construction (D8.3): the certificate carries its own
    snapshot, so a later scale change cannot retroactively flip who passed."""
    _course(db, "c-cert")
    cert = Certificate(
        id=uuid.uuid4(),
        user_id=STUDENT_ID,
        course_id="c-cert",
        status=CertificateStatus.APPROVED,
        issued_at=datetime.now(UTC),
        grading_scheme="letter",
        pass_threshold=Decimal("70"),
        official_code="B",
    )
    db.add(cert)
    db.commit()

    admin_client.put(URL, json={"grade_bands": {"letter": UA_LETTERS}})

    db.refresh(cert)
    assert cert.official_code == "B"
