"""The name on the certificate does not depend on who is reading it.

Every other word on the document was frozen at issuance — the school,
the city, the student, the teacher. The course title was not: the verify
endpoint resolved it from ``content_versions`` at the verifier's own
``Accept-Language``, with ``Vary: Accept-Language`` on the response.

So an employer in Berlin and an employer in Kyiv checking the same
credential saw different course names, and both would change again the
next time someone re-ran the translation. The one field a stranger
actually reads was the one field that could still move.

It is captured in English, not in the recipient's language, for the same
reason the grade sheet is: a certificate is read by people with no
account here, possibly years later. It has to say the same thing to all
of them.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.certificate import Certificate, CertificateStatus
from app.models.course import Course
from app.models.user import User
from app.services.certificate_service import _snapshot_letterhead
from app.services.content_versions import record_human_version, record_mt_version
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

RU_TITLE = "Обзор книги Бытия"
EN_TITLE = "Genesis Overview"


def _seed_teacher(db: Session) -> None:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", role="teacher"))
        db.commit()


def _make_course(db: Session) -> Course:
    _seed_teacher(db)
    course = Course(
        id=str(uuid.uuid4()),
        title=RU_TITLE,
        description="Введение.",
        created_by=TEACHER_ID,
        status="published",
        source_locale="ru",
    )
    db.add(course)
    db.commit()

    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="ru",
        text=RU_TITLE,
    )
    record_mt_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="en",
        text=EN_TITLE,
        source_locale="ru",
        source_hash="hash",
    )
    db.commit()
    return course


def _issue(db: Session, course: Course, *, number: str) -> Certificate:
    cert = Certificate(
        id=uuid.uuid4(),
        user_id=TEACHER_ID,
        course_id=course.id,
        status=CertificateStatus.APPROVED,
        certificate_number=number,
    )
    db.add(cert)
    db.commit()
    _snapshot_letterhead(db, cert, course)
    db.commit()
    return cert


class TestIssuance:
    def test_the_title_is_captured_in_english(self, db: Session):
        course = _make_course(db)
        cert = _issue(db, course, number="CERT-FROZEN00001")

        assert cert.course_title == EN_TITLE

    def test_a_later_retranslation_does_not_rewrite_it(self, db: Session):
        course = _make_course(db)
        cert = _issue(db, course, number="CERT-FROZEN00002")

        # Somebody re-runs the pipeline and the English wording changes.
        record_mt_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale="en",
            text="An Overview of Genesis",
            source_locale="ru",
            source_hash="hash-2",
        )
        db.commit()
        db.refresh(cert)

        assert cert.course_title == EN_TITLE

    def test_a_course_with_no_english_still_gets_a_title(self, db: Session):
        # A course from before the publication gate, or one whose English
        # is still being checked. A title in the wrong language beats a
        # blank line on a document someone has to show an employer.
        _seed_teacher(db)
        course = Course(
            id=str(uuid.uuid4()),
            title=RU_TITLE,
            created_by=TEACHER_ID,
            status="published",
            source_locale="ru",
        )
        db.add(course)
        db.commit()
        record_human_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale="ru",
            text=RU_TITLE,
        )
        db.commit()

        cert = _issue(db, course, number="CERT-FROZEN00003")
        assert cert.course_title == RU_TITLE


class TestVerification:
    @pytest.mark.parametrize("accept_language", ["en", "ru", "de-DE,de;q=0.9", None])
    def test_every_verifier_sees_the_same_name(
        self,
        client: TestClient,
        db: Session,
        accept_language: str | None,
    ):
        course = _make_course(db)
        _issue(db, course, number="CERT-FROZEN00004")

        headers = {"Accept-Language": accept_language} if accept_language else {}
        response = client.get("/api/v1/certificates/verify/CERT-FROZEN00004", headers=headers)

        assert response.status_code == 200
        assert response.json()["course_title"] == EN_TITLE

    def test_the_response_no_longer_varies_by_language(self, client: TestClient, db: Session):
        course = _make_course(db)
        _issue(db, course, number="CERT-FROZEN00005")

        response = client.get("/api/v1/certificates/verify/CERT-FROZEN00005")

        assert response.status_code == 200
        assert "Accept-Language" not in response.headers.get("Vary", "")

    def test_a_certificate_issued_before_the_snapshot_still_verifies(
        self,
        client: TestClient,
        db: Session,
    ):
        course = _make_course(db)
        cert = _issue(db, course, number="CERT-FROZEN00006")
        # Back to how rows looked before this change.
        cert.course_title = None
        db.commit()

        response = client.get("/api/v1/certificates/verify/CERT-FROZEN00006")

        assert response.status_code == 200
        assert response.json()["course_title"] == EN_TITLE
