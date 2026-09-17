"""The audit log records who did what and when -- never where from.

The Privacy Policy says an IP address is kept at exactly two moments: accepting
a legal document and handing in work, because those two records have to be
shown to have actually been made. Everything else a person does -- enrolling,
changing a setting, creating a course, marking work -- is audited without it.

Until September 2026 ``log_action`` read the client IP and User-Agent off every
request it was given and wrote them into ``audit_logs``: 638 rows of 652 held an
address the policy said was never kept. The columns are gone now, and these
tests make sure no path quietly starts writing it again -- not a re-added
column, not a ``Request`` threaded back into ``log_action``, and not an address
tucked into the free-form ``details`` JSON.

The two records that *are* promised an IP are exercised here as well. They are
the control: they prove the request in these tests really carries a resolvable
client address, so the audit rows staying clean means something.
"""

from __future__ import annotations

import inspect
import json
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.core import http as core_http
from app.legal import LEGAL_DOCUMENTS
from app.main import app
from app.models.assignment import Assignment
from app.models.audit_log import AuditLog
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.legal_acceptance import LegalAcceptance
from app.models.submission_declaration import SubmissionDeclaration
from app.services import audit_service

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

from .conftest import STUDENT_ID, TEACHER_ID

CLIENT_IP = "203.0.113.77"
USER_AGENT = "EquipAuditProbe/1.0 (no-ip-in-audit-log)"
HEADERS = {"x-vercel-forwarded-for": CLIENT_IP, "user-agent": USER_AGENT}

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "supabase" / "schema.sql"

# Column names that would mean somebody is keeping a network identity again.
_NETWORK_COLUMN = re.compile(r"(^|_)(ip|ips|inet|addr|address|agent|ua|useragent)($|_)", re.IGNORECASE)


@pytest.fixture(autouse=True)
def _behind_vercel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the client IP the way production does, from Vercel's header."""
    monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)


def _seed_assignment(db: Session) -> Assignment:
    course_id = "no-ip-course"
    db.add(Course(id=course_id, status="published", created_by=TEACHER_ID, ai_policy="ai_with_disclosure"))
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.flush()
    chapter = Chapter(id=f"{course_id}-a", module_id=module.id, order_index=0, chapter_type="assignment", title="Эссе")
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=10)
    db.add(assignment)
    # A second published course with no seat taken yet, to enroll in.
    db.add(Course(id="no-ip-open-course", status="published", created_by=TEACHER_ID))
    db.commit()
    return assignment


def _as(user: User) -> None:
    from app.api.dependencies import get_current_user, get_optional_user

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user


def _rendered(row: AuditLog) -> str:
    """Every stored value of a row as one string, ``details`` included."""
    values = {column.name: getattr(row, column.key) for column in AuditLog.__table__.columns}
    return json.dumps(values, default=str, ensure_ascii=False)


def test_audited_actions_leave_no_ip_or_user_agent(
    student_client: TestClient, db: Session, teacher: User, student: User
) -> None:
    assignment = _seed_assignment(db)

    # Student: accept the privacy policy, change a setting, enroll, hand in work.
    accepted = student_client.post(
        "/api/v1/legal/acceptances",
        json={"slug": "privacy", "version": LEGAL_DOCUMENTS["privacy"], "locale": "en"},
        headers=HEADERS,
    )
    assert accepted.status_code == 201, accepted.text
    prefs = student_client.patch("/api/v1/users/me/preferences", json={"preferred_locale": "de"}, headers=HEADERS)
    assert prefs.status_code == 200, prefs.text
    enrolled = student_client.post("/api/v1/courses/no-ip-open-course/enroll", headers=HEADERS)
    assert enrolled.status_code in (200, 201), enrolled.text
    submitted = student_client.post(
        f"/api/v1/assignments/{assignment.id}/submit",
        json={"content": "Работа", "declaration": {"ai_use": "none", "statement": "Я написал эту работу сам."}},
        headers=HEADERS,
    )
    assert submitted.status_code == 201, submitted.text

    # Teacher: create a course and mark the work.
    _as(teacher)
    created = student_client.post("/api/v1/courses", json={"title": "Acts"}, headers=HEADERS)
    assert created.status_code in (200, 201), created.text
    graded = student_client.put(
        f"/api/v1/assignments/submissions/{submitted.json()['id']}/grade",
        json={"grade": 8, "feedback": "Хорошо", "status": "graded"},
        headers=HEADERS,
    )
    assert graded.status_code == 200, graded.text

    # Control: the two records the policy names did get the address, so the
    # request really carried one.
    assert db.query(LegalAcceptance).one().ip == CLIENT_IP
    assert db.query(SubmissionDeclaration).one().ip == CLIENT_IP

    rows = db.query(AuditLog).all()
    actions = {(row.action, row.resource_type) for row in rows}
    # Enough different writers were exercised for "none of them" to mean something.
    assert len(actions) >= 4, actions
    for row in rows:
        stored = _rendered(row)
        assert CLIENT_IP not in stored, f"{row!r} keeps the client IP: {stored}"
        assert USER_AGENT not in stored, f"{row!r} keeps the User-Agent: {stored}"


def test_the_audit_log_model_has_nowhere_to_put_an_address() -> None:
    offending = [c.name for c in AuditLog.__table__.columns if _NETWORK_COLUMN.search(c.name)]
    assert offending == [], f"audit_logs has network-identity columns again: {offending}"


def test_log_action_cannot_be_handed_a_request() -> None:
    """A ``Request`` is where an IP comes from; ``log_action`` never sees one."""
    params = inspect.signature(audit_service.log_action).parameters
    assert "request" not in params
    # Annotations stay strings under ``from __future__ import annotations``.
    annotations = inspect.get_annotations(audit_service.log_action)
    assert not [name for name, hint in annotations.items() if "Request" in str(hint)], annotations


def test_the_committed_schema_matches() -> None:
    """``supabase/schema.sql`` is what a rebuilt database looks like."""
    match = re.search(r"CREATE TABLE public\.audit_logs \((.*?)\n\);", SCHEMA_SQL.read_text(), re.DOTALL)
    assert match, "audit_logs table not found in supabase/schema.sql"
    columns = [line.strip().split()[0] for line in match.group(1).strip().splitlines()]
    offending = [name for name in columns if _NETWORK_COLUMN.search(name)]
    assert offending == [], f"schema.sql audit_logs has network-identity columns: {offending}"
