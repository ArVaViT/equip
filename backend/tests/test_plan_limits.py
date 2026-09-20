"""The plan's limits — what an account may hold, and every door it holds it through.

The course cap used to live inline in ``POST /courses`` and nowhere else,
so the two other routes that hand a teacher a live course — clone and
restore-from-trash — walked straight past it. These tests pin all three
doors, plus the resolution order that lets the number move.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User, UserRole
from app.services.limits import BASE_PLAN, LimitKey, limit_for
from tests.conftest import TEACHER_ID

pytestmark = pytest.mark.usefixtures("two_locales")
PREFIX = "/api/v1/courses"


def _create(client: TestClient, title: str) -> dict:
    resp = client.post(PREFIX, json={"title": title, "description": "x"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _fill_to_the_cap(client: TestClient, cap: int) -> list[dict]:
    return [_create(client, f"Course {n}") for n in range(cap)]


class TestTheBasePlan:
    def test_base_plan_allows_five_courses(self, client: TestClient):
        """The shipped number. Written out rather than read from the plan,
        so changing the plan is a deliberate edit to this line too."""
        assert BASE_PLAN[LimitKey.COURSES_PER_TEACHER] == 5
        _fill_to_the_cap(client, 5)

        resp = client.post(PREFIX, json={"title": "Sixth"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "plan.limit_reached"

    def test_a_deployment_override_beats_the_plan(self, teacher: User, monkeypatch: pytest.MonkeyPatch):
        """The dial that exists today: one env var, no deploy of new code."""
        assert limit_for(teacher, LimitKey.COURSES_PER_TEACHER) == 5
        monkeypatch.setattr(settings, "MAX_COURSES_PER_TEACHER", 12)
        assert limit_for(teacher, LimitKey.COURSES_PER_TEACHER) == 12


class TestEveryDoorToANewCourse:
    """Create is not the only way a teacher ends up holding one more."""

    def test_clone_is_capped(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "MAX_COURSES_PER_TEACHER", 2)
        first, _ = _fill_to_the_cap(client, 2)

        resp = client.post(f"{PREFIX}/{first['id']}/clone")
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "plan.limit_reached"

    def test_clone_works_below_the_cap(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "MAX_COURSES_PER_TEACHER", 3)
        first, _ = _fill_to_the_cap(client, 2)

        resp = client.post(f"{PREFIX}/{first['id']}/clone")
        assert resp.status_code == 201, resp.text

    def test_restore_from_trash_is_capped(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Trash is not a parking space. A teacher who deletes one course,
        creates another and then asks for the first one back is over the
        cap either way — and the answer has to be the same."""
        monkeypatch.setattr(settings, "MAX_COURSES_PER_TEACHER", 2)
        first, _ = _fill_to_the_cap(client, 2)

        assert client.delete(f"{PREFIX}/{first['id']}").status_code in (200, 204)
        _create(client, "Replacement")

        resp = client.post(f"{PREFIX}/{first['id']}/restore")
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "plan.limit_reached"

    def test_restore_works_when_a_slot_is_free(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "MAX_COURSES_PER_TEACHER", 2)
        first, _ = _fill_to_the_cap(client, 2)

        assert client.delete(f"{PREFIX}/{first['id']}").status_code in (200, 204)
        resp = client.post(f"{PREFIX}/{first['id']}/restore")
        assert resp.status_code == 200, resp.text


class TestAdminsAreNotMetered:
    def test_admin_clones_past_the_cap(self, client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "MAX_COURSES_PER_TEACHER", 2)
        first, _ = _fill_to_the_cap(client, 2)

        teacher = db.query(User).filter(User.id == TEACHER_ID).one()
        teacher.role = UserRole.ADMIN.value
        db.commit()

        assert client.post(f"{PREFIX}/{first['id']}/clone").status_code == 201
