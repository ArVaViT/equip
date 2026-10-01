# ruff: noqa: RUF001
# The fixtures are Russian course text; Cyrillic letters that look like
# Latin ones are the content, not a slip.
"""A certificate's decision reaches the student by mail, once, in their language.

Issued: the number and where anyone can check it. Not approved: the way
back to the course. Course mail of the kind ``certificate_decided``, so a
student who turned it off gets the decision in the app and no mail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from app.models.certificate import Certificate
from app.services import certificate_service
from app.services.email import course_mail
from tests._cv_helpers import make_course_with_text
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


def _cert(db: Session, status: str) -> Certificate:
    course = make_course_with_text(db, title="Деяния", status="published", created_by=TEACHER_ID, source_locale="ru")
    cert = Certificate(user_id=STUDENT_ID, course_id=course.id, status=status)
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def test_an_issued_certificate_mails_its_number_and_where_to_check_it(
    db: Session, teacher: User, student: User, admin: User
) -> None:
    student.preferred_locale = "ru"
    db.commit()
    cert = _cert(db, "teacher_approved")
    sent: list[dict] = []
    with patch.object(course_mail, "send_email", side_effect=lambda **kw: sent.append(kw)):
        certificate_service.admin_approve(db, cert.id, admin)
    [mail] = sent
    assert mail["kind"] == "certificate_decided"
    assert mail["subject"] == "Свидетельство о курсе «Деяния» выдано"
    assert cert.certificate_number and cert.certificate_number in mail["html"]
    assert f"/verify/{cert.certificate_number}" in mail["html"]


def test_a_rejected_request_mails_the_way_back_to_the_course(db: Session, teacher: User, student: User) -> None:
    cert = _cert(db, "pending")
    sent: list[dict] = []
    with patch.object(course_mail, "send_email", side_effect=lambda **kw: sent.append(kw)):
        certificate_service.reject(db, cert.id, teacher)
    [mail] = sent
    assert "не одобрен" in mail["subject"] or "was not approved" in mail["subject"]
    assert f"/courses/{cert.course_id}" in mail["html"]


def test_a_student_who_stopped_it_gets_no_mail(db: Session, teacher: User, student: User, admin: User) -> None:
    student.email_off = ["certificate_decided"]
    db.commit()
    cert = _cert(db, "teacher_approved")
    with patch.object(course_mail, "send_email") as send:
        certificate_service.admin_approve(db, cert.id, admin)
    send.assert_not_called()
    assert cert.status == "approved"
