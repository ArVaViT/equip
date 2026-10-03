"""A completed cohort is history: nothing new goes into it (2026-10-03).

Its grades and certificates are frozen (update_cohort refuses to reopen it),
yet a course could still be attached and a student added — new enrolments in
a term that is over.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.cohort import Cohort, CohortStatus
from app.models.course import Course

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def test_a_completed_cohort_refuses_a_course_and_a_student(
    admin_client: TestClient, db: Session, teacher, student
) -> None:
    now = datetime.now(UTC)
    cohort = Cohort(
        id=uuid.uuid4(),
        start_date=now - timedelta(days=90),
        end_date=now - timedelta(days=1),
        status=CohortStatus.COMPLETED,
    )
    db.add(cohort)
    db.add(Course(id="c-done-cohort", status="published", created_by=teacher.id))
    db.commit()

    attach = admin_client.post(f"/api/v1/cohorts/{cohort.id}/courses", json={"course_id": "c-done-cohort"})
    add = admin_client.post(f"/api/v1/cohorts/{cohort.id}/students", json={"user_id": str(STUDENT_ID)})

    assert attach.status_code == 409, attach.text
    assert add.status_code == 409, add.text
