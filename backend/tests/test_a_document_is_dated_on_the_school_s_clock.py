"""A school's documents carry the school's day, for every reader.

The API used to hand out the instant alone, and each screen picked the day in
its reader's zone: a certificate signed at 23:30 in Indianapolis on October 24
was dated the 25th in Kyiv — on the document, the transcript, the public
verification page and the LinkedIn link. ``issued_on`` (and the ведомость's
``finalized_on``) is that day on the school's clock (``org_settings.time_zone``,
else Indianapolis), computed once, on the server.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.models.certificate import Certificate, CertificateStatus
from app.models.course import Course
from app.models.grade_sheet import GradeSheet
from app.services.grading_scheme import get_org_settings
from app.services.school_clock import day_on, school_time_zone

from .conftest import STUDENT_ID, TEACHER_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

# 23:30 EDT on Saturday October 24, 2026 — already Sunday the 25th in UTC and in Kyiv.
LATE_IN_INDIANA = datetime(2026, 10, 25, 3, 30, tzinfo=UTC)
# 00:30 EEST on Monday October 5 in Kyiv — still Sunday the 4th in UTC and in Indiana.
EARLY_IN_KYIV = datetime(2026, 10, 4, 21, 30, tzinfo=UTC)


def _school(db: Session, zone: str | None) -> None:
    get_org_settings(db, TEST_ORGANIZATION_ID).time_zone = zone
    db.commit()


def _issued(db: Session, at: datetime) -> Certificate:
    course_id = f"c-doc-{uuid.uuid4().hex[:6]}"
    db.add(
        Course(
            id=course_id,
            status="published",
            created_by=TEACHER_ID,
            grading_scheme="letter",
            organization_id=TEST_ORGANIZATION_ID,
        )
    )
    db.flush()
    cert = Certificate(
        id=uuid.uuid4(),
        organization_id=TEST_ORGANIZATION_ID,
        user_id=STUDENT_ID,
        course_id=course_id,
        course_title="Preaching I",
        status=CertificateStatus.APPROVED,
        issued_at=at,
        certificate_number=f"CERT-{uuid.uuid4().hex[:12].upper()}",
        grading_scheme="letter",
        pass_threshold=Decimal("70"),
        official_code="B",
    )
    db.add(cert)
    db.commit()
    return cert


CASES = [
    pytest.param(None, LATE_IN_INDIANA, "2026-10-24", id="default-school-late-in-indiana"),
    pytest.param("America/Indiana/Indianapolis", LATE_IN_INDIANA, "2026-10-24", id="indiana-school"),
    pytest.param("Europe/Kyiv", LATE_IN_INDIANA, "2026-10-25", id="kyiv-school-same-instant"),
    pytest.param("Europe/Kyiv", EARLY_IN_KYIV, "2026-10-05", id="kyiv-school-early-in-kyiv"),
    pytest.param(None, EARLY_IN_KYIV, "2026-10-04", id="default-school-early-in-kyiv"),
]


@pytest.mark.parametrize(("zone", "at", "day"), CASES)
def test_the_student_s_certificates_carry_the_school_s_day(
    student_client: TestClient, db: Session, student: User, zone: str | None, at: datetime, day: str
) -> None:
    _school(db, zone)
    cert = _issued(db, at)

    mine = student_client.get("/api/v1/certificates/my")
    assert mine.status_code == 200, mine.text
    assert [c["issued_on"] for c in mine.json()] == [day]

    one = student_client.get(f"/api/v1/certificates/course/{cert.course_id}")
    assert one.json()["issued_on"] == day
    # The instant is still there for anything that is not a date.
    assert one.json()["issued_at"].startswith(at.strftime("%Y-%m-%dT%H:%M"))


@pytest.mark.parametrize(("zone", "at", "day"), CASES)
def test_the_public_verification_carries_the_same_day(
    client: TestClient, db: Session, zone: str | None, at: datetime, day: str
) -> None:
    _school(db, zone)
    cert = _issued(db, at)

    r = client.get(f"/api/v1/certificates/verify/{cert.certificate_number}")

    assert r.status_code == 200, r.text
    assert r.json()["valid"] is True
    assert r.json()["issued_on"] == day


def test_a_certificate_not_yet_issued_has_no_day(student_client: TestClient, db: Session, student: User) -> None:
    cert = _issued(db, LATE_IN_INDIANA)
    cert.status = CertificateStatus.PENDING
    cert.issued_at = None
    db.commit()

    r = student_client.get(f"/api/v1/certificates/course/{cert.course_id}")

    assert r.json()["issued_on"] is None


@pytest.mark.parametrize(
    ("zone", "closed_on", "start_on"),
    [
        (None, "2026-10-24", "2026-09-01"),
        ("Europe/Kyiv", "2026-10-25", "2026-09-01"),
    ],
)
def test_the_vedomost_carries_the_school_s_days(
    client: TestClient, db: Session, teacher: User, zone: str | None, closed_on: str, start_on: str
) -> None:
    _school(db, zone)
    course_id = f"c-sheet-{uuid.uuid4().hex[:6]}"
    db.add(
        Course(
            id=course_id,
            status="published",
            created_by=TEACHER_ID,
            grading_scheme="letter",
            organization_id=TEST_ORGANIZATION_ID,
        )
    )
    db.flush()
    db.add(
        GradeSheet(
            id=uuid.uuid4(),
            organization_id=TEST_ORGANIZATION_ID,
            course_id=course_id,
            locale="ru",
            grading_scheme="letter",
            pass_threshold=Decimal("70"),
            # Noon UTC: the first of September on both clocks.
            cohort_start=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            finalized_at=LATE_IN_INDIANA,
            finalized_by=TEACHER_ID,
        )
    )
    db.commit()

    r = client.get(f"/api/v1/grades/course/{course_id}/sheet")

    assert r.status_code == 200, r.text
    assert r.json()["finalized_on"] == closed_on
    assert r.json()["cohort_start_on"] == start_on
    assert r.json()["cohort_end_on"] is None


def test_a_school_without_settings_or_with_a_hand_written_typo_keeps_indiana(db: Session) -> None:
    assert str(school_time_zone(db, uuid.uuid4())) == "America/Indiana/Indianapolis"
    assert str(school_time_zone(db, None)) == "America/Indiana/Indianapolis"
    _school(db, "Europe/Kiyv")  # only reachable by hand: the API refuses it
    assert str(school_time_zone(db, TEST_ORGANIZATION_ID)) == "America/Indiana/Indianapolis"
    assert day_on(school_time_zone(db, None), LATE_IN_INDIANA.replace(tzinfo=None)) == date(2026, 10, 24)
