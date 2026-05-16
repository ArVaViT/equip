"""Tests for the /api/v1/courses endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.content_translation import ContentTranslation
from app.models.course import Course
from app.services.translation.orchestrator import OrchestratorReport
from tests.conftest import TEACHER_ID

PREFIX = "/api/v1/courses"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_course(client: TestClient, **overrides) -> dict:
    payload = {"title": "Genesis Overview", "description": "An intro course"}
    payload.update(overrides)
    resp = client.post(PREFIX, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCreateCourse:
    def test_create_returns_201(self, client: TestClient):
        data = _create_course(client)
        assert data["title"] == "Genesis Overview"
        assert data["status"] == "draft"
        assert data["created_by"] == str(TEACHER_ID)

    def test_create_without_title_returns_422(self, client: TestClient):
        resp = client.post(PREFIX, json={"description": "no title"})
        assert resp.status_code == 422


class TestListCourses:
    def test_empty_list(self, client: TestClient):
        resp = client.get(PREFIX)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_published_courses(self, client: TestClient):
        course = _create_course(client)
        course_id = course["id"]

        client.put(
            f"{PREFIX}/{course_id}",
            json={"status": "published"},
        )

        resp = client.get(PREFIX)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert course_id in ids

    def test_draft_courses_not_listed(self, client: TestClient):
        _create_course(client)
        resp = client.get(PREFIX)
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetCourse:
    def test_get_existing_course(self, client: TestClient):
        course = _create_course(client)
        resp = client.get(f"{PREFIX}/{course['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == course["id"]

    def test_get_nonexistent_returns_404(self, client: TestClient):
        resp = client.get(f"{PREFIX}/nonexistent-id")
        assert resp.status_code == 404


class TestUpdateCourse:
    def test_update_title(self, client: TestClient):
        course = _create_course(client)
        resp = client.put(
            f"{PREFIX}/{course['id']}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    def test_publish_course(self, client: TestClient):
        course = _create_course(client)
        resp = client.put(
            f"{PREFIX}/{course['id']}",
            json={"status": "published"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

    def test_update_nonexistent_returns_404(self, client: TestClient):
        resp = client.put(
            f"{PREFIX}/nonexistent-id",
            json={"title": "Nope"},
        )
        assert resp.status_code == 404


class TestDeleteCourse:
    def test_delete_existing_course(self, client: TestClient):
        course = _create_course(client)
        resp = client.delete(f"{PREFIX}/{course['id']}")
        assert resp.status_code == 204

        resp = client.get(f"{PREFIX}/{course['id']}")
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client: TestClient):
        resp = client.delete(f"{PREFIX}/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


class TestEnrollment:
    def test_enroll_in_published_course(self, student_client: TestClient, client: TestClient):
        course = _create_course(client)
        client.put(f"{PREFIX}/{course['id']}", json={"status": "published"})

        resp = student_client.post(f"{PREFIX}/{course['id']}/enroll")
        assert resp.status_code == 200
        body = resp.json()
        assert body["course_id"] == course["id"]
        assert body["progress"] == 0

    def test_enroll_is_idempotent(self, student_client: TestClient, client: TestClient):
        course = _create_course(client)
        client.put(f"{PREFIX}/{course['id']}", json={"status": "published"})

        resp1 = student_client.post(f"{PREFIX}/{course['id']}/enroll")
        resp2 = student_client.post(f"{PREFIX}/{course['id']}/enroll")
        assert resp1.json()["id"] == resp2.json()["id"]

    def test_enroll_nonexistent_course_returns_404(self, student_client: TestClient):
        resp = student_client.post(f"{PREFIX}/nonexistent-id/enroll")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------


class TestCloneCourse:
    def test_clone_own_course(self, client: TestClient):
        course = _create_course(client, title="Original")
        resp = client.post(f"{PREFIX}/{course['id']}/clone")
        assert resp.status_code == 201
        clone = resp.json()
        assert clone["id"] != course["id"]
        assert "Copy" in clone["title"]
        assert clone["status"] == "draft"

    def test_clone_nonexistent_returns_404(self, client: TestClient):
        resp = client.post(f"{PREFIX}/nonexistent-id/clone")
        assert resp.status_code == 404

    def test_clone_copies_chapter_blocks_and_essay_questions(self, client: TestClient):
        """Regression: clone must propagate storage pointers and essay hints.

        Before the audit fix, ``clone_course`` still referenced the retired
        ``file_url`` column and silently dropped ``min_words``, so any course
        with file blocks or essay prompts came back incomplete.
        """
        course = _create_course(client, title="Has Files & Essay")
        mod_resp = client.post(
            f"{PREFIX}/{course['id']}/modules",
            json={"title": "M1", "order_index": 1},
        )
        assert mod_resp.status_code == 201
        module_id = mod_resp.json()["id"]

        ch_resp = client.post(
            f"{PREFIX}/{course['id']}/modules/{module_id}/chapters",
            json={"title": "Ch1", "chapter_type": "quiz", "order_index": 1},
        )
        assert ch_resp.status_code == 201
        chapter_id = ch_resp.json()["id"]

        quiz_resp = client.post(
            "/api/v1/quizzes",
            json={
                "chapter_id": chapter_id,
                "title": "Essay Quiz",
                "passing_score": 60,
                "questions": [
                    {
                        "question_text": "Write an essay on Acts 2.",
                        "question_type": "essay",
                        "order_index": 1,
                        "points": 10,
                        "min_words": 150,
                        "options": [],
                    }
                ],
            },
        )
        assert quiz_resp.status_code == 201, quiz_resp.text

        block_resp = client.post(
            f"/api/v1/blocks/chapter/{chapter_id}",
            json={
                "block_type": "file",
                "order_index": 0,
                "file_bucket": "course-materials",
                "file_path": f"{chapter_id}/lecture.pdf",
                "file_name": "lecture.pdf",
            },
        )
        assert block_resp.status_code == 201, block_resp.text

        clone_resp = client.post(f"{PREFIX}/{course['id']}/clone")
        assert clone_resp.status_code == 201, clone_resp.text
        clone = clone_resp.json()

        cloned_chapter_id = clone["modules"][0]["chapters"][0]["id"]

        cloned_blocks = client.get(f"/api/v1/blocks/chapter/{cloned_chapter_id}").json()
        assert len(cloned_blocks) == 1
        assert cloned_blocks[0]["file_bucket"] == "course-materials"
        assert cloned_blocks[0]["file_path"].endswith("/lecture.pdf")
        assert cloned_blocks[0]["file_name"] == "lecture.pdf"

        cloned_quiz_resp = client.get(f"/api/v1/quizzes/chapter/{cloned_chapter_id}")
        assert cloned_quiz_resp.status_code == 200
        cloned_quiz = cloned_quiz_resp.json()
        assert cloned_quiz["questions"][0]["question_type"] == "essay"
        assert cloned_quiz["questions"][0]["min_words"] == 150


# ---------------------------------------------------------------------------
# Localized catalog (content_translations read path)
# ---------------------------------------------------------------------------


class TestCatalogLocalizedMetadata:
    def _seed_en_translations(self, db: Session, course_id: str) -> None:
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=course_id,
                field="title",
                locale="en",
                text="English catalog title",
                source_hash="testhash",
                status="ok",
                origin="mt",
            )
        )
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=course_id,
                field="description",
                locale="en",
                text="English catalog description",
                source_hash="testhash2",
                status="ok",
                origin="mt",
            )
        )
        db.commit()

    def test_list_applies_translations_for_accept_language(
        self,
        client: TestClient,
        db: Session,
        anon_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.api.v1.courses.crud.translate_course_content",
            lambda *args, **kwargs: OrchestratorReport(),
        )
        course = _create_course(
            client,
            title="Заголовок RU",
            description="Описание RU",
        )
        cid = course["id"]
        client.put(
            f"{PREFIX}/{cid}",
            json={"status": "published"},
        )
        self._seed_en_translations(db, cid)

        r_ru = anon_client.get(PREFIX, headers={"Accept-Language": "ru"})
        assert r_ru.status_code == 200
        row = next(c for c in r_ru.json() if c["id"] == cid)
        assert row["title"] == "Заголовок RU"
        assert row["description"] == "Описание RU"

        r_en = anon_client.get(PREFIX, headers={"Accept-Language": "en"})
        assert r_en.status_code == 200
        row_en = next(c for c in r_en.json() if c["id"] == cid)
        assert row_en["title"] == "English catalog title"
        assert row_en["description"] == "English catalog description"

    def test_get_detail_owner_sees_source_when_ui_is_en(
        self,
        client: TestClient,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Do not request ``anon_client`` in the same test: it shares
        # ``app.dependency_overrides`` and whichever fixture runs last would
        # clobber the other's ``get_optional_user`` override.
        monkeypatch.setattr(
            "app.api.v1.courses.crud.translate_course_content",
            lambda *args, **kwargs: OrchestratorReport(),
        )
        course = _create_course(
            client,
            title="Заголовок RU",
            description="Описание RU",
        )
        cid = course["id"]
        client.put(f"{PREFIX}/{cid}", json={"status": "published"})
        self._seed_en_translations(db, cid)

        owner = client.get(
            f"{PREFIX}/{cid}",
            headers={"Accept-Language": "en"},
        )
        assert owner.status_code == 200
        assert owner.json()["title"] == "Заголовок RU"

    def test_get_detail_anon_sees_translated_metadata_with_accept_language(
        self,
        client: TestClient,
        db: Session,
        anon_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.api.v1.courses.crud.translate_course_content",
            lambda *args, **kwargs: OrchestratorReport(),
        )
        course = _create_course(
            client,
            title="Заголовок RU",
            description="Описание RU",
        )
        cid = course["id"]
        client.put(f"{PREFIX}/{cid}", json={"status": "published"})
        self._seed_en_translations(db, cid)

        r = anon_client.get(
            f"{PREFIX}/{cid}",
            headers={"Accept-Language": "en"},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "English catalog title"

    def test_get_detail_source_param_returns_raw_columns_for_owner(
        self,
        client: TestClient,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``?source=1`` bypasses the overlay even with an explicit EN
        ``Accept-Language``. This is the editor-page escape hatch — without
        it a teacher in EN UI viewing their RU course would see EN text in
        the inline-edit fields and a PATCH would overwrite the source
        ``title`` column with English.
        """
        monkeypatch.setattr(
            "app.api.v1.courses.crud.translate_course_content",
            lambda *args, **kwargs: OrchestratorReport(),
        )
        course = _create_course(
            client,
            title="Заголовок RU",
            description="Описание RU",
        )
        cid = course["id"]
        client.put(f"{PREFIX}/{cid}", json={"status": "published"})
        self._seed_en_translations(db, cid)

        # Sanity check: the same endpoint without ``?source=1`` still applies
        # the EN overlay for the owner once we remove the implicit owner skip
        # (today's main still skips for owner, so the assertion here is the
        # source contract — that ``?source=1`` always returns source).
        owner_with_source = client.get(
            f"{PREFIX}/{cid}",
            params={"source": "1"},
            headers={"Accept-Language": "en"},
        )
        assert owner_with_source.status_code == 200
        body = owner_with_source.json()
        assert body["title"] == "Заголовок RU"
        assert body["description"] == "Описание RU"

    def test_get_detail_source_param_returns_raw_columns_for_admin(
        self,
        admin_client: TestClient,
        client: TestClient,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Admins managing a teacher's course also need source columns for
        editor surfaces. ``client`` seeds the teacher + course; ``admin_client``
        then opens the same course."""
        monkeypatch.setattr(
            "app.api.v1.courses.crud.translate_course_content",
            lambda *args, **kwargs: OrchestratorReport(),
        )
        course = _create_course(
            client,
            title="Заголовок RU",
            description="Описание RU",
        )
        cid = course["id"]
        client.put(f"{PREFIX}/{cid}", json={"status": "published"})
        self._seed_en_translations(db, cid)

        resp = admin_client.get(
            f"{PREFIX}/{cid}",
            params={"source": "1"},
            headers={"Accept-Language": "en"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Заголовок RU"
        assert body["description"] == "Описание RU"

    def test_get_detail_source_param_403_for_non_owner_student(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        """Source content can include unredacted teacher drafts / typos —
        returning it to a regular student would be an information leak.
        The endpoint denies loudly (403) so frontend regressions surface
        immediately instead of leaking text on a slow rollout."""
        # Seed via the DB directly so we don't share ``dependency_overrides``
        # with another TestClient fixture (only ``student_client`` is in play).
        course = Course(
            id="course-source-403",
            title="Заголовок RU",
            description="Описание RU",
            status="published",
            created_by=TEACHER_ID,
        )
        db.add(course)
        db.commit()
        self._seed_en_translations(db, course.id)

        resp = student_client.get(
            f"{PREFIX}/{course.id}",
            params={"source": "1"},
            headers={"Accept-Language": "en"},
        )
        assert resp.status_code == 403

    def test_get_module_detail_source_param_returns_raw_columns_for_owner(
        self,
        client: TestClient,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The module-detail editor endpoint (``CourseEditor`` opens it for
        each module via ``ModuleEditor``) must hand back source columns even
        when the viewer is in EN UI."""
        monkeypatch.setattr(
            "app.api.v1.courses.crud.translate_course_content",
            lambda *args, **kwargs: OrchestratorReport(),
        )
        course = _create_course(client, title="RU course", description="RU desc")
        cid = course["id"]
        client.put(f"{PREFIX}/{cid}", json={"status": "published"})

        mod_resp = client.post(
            f"{PREFIX}/{cid}/modules",
            json={"title": "Модуль RU", "description": "Описание модуля", "order_index": 0},
        )
        assert mod_resp.status_code == 201, mod_resp.text
        mod_id = mod_resp.json()["id"]

        db.add(
            ContentTranslation(
                entity_type="module",
                entity_id=str(mod_id),
                field="title",
                locale="en",
                text="Module title EN",
                source_hash="m1",
                status="ok",
                origin="mt",
            )
        )
        db.commit()

        resp = client.get(
            f"{PREFIX}/{cid}/modules/{mod_id}",
            params={"source": "1"},
            headers={"Accept-Language": "en"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Модуль RU"

    def test_get_module_detail_source_param_403_for_non_owner_student(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        from app.models.course import Module

        course = Course(
            id="course-mod-source-403",
            title="RU course",
            description="RU desc",
            status="published",
            created_by=TEACHER_ID,
        )
        module = Module(
            id="mod-source-403",
            course_id=course.id,
            title="Модуль RU",
            description="x",
            order_index=0,
        )
        db.add_all([course, module])
        db.commit()

        # ``get_module_detail`` doesn't enforce enrollment for published
        # courses — any authenticated user can call it. The 403 must come
        # from the ``?source=1`` gate, not from enrollment.
        resp = student_client.get(
            f"{PREFIX}/{course.id}/modules/{module.id}",
            params={"source": "1"},
            headers={"Accept-Language": "en"},
        )
        assert resp.status_code == 403

    def test_ru_ct_row_preferred_over_course_columns_when_source_locale_mismatch(
        self,
        client: TestClient,
        db: Session,
        anon_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``content_translations`` for the active UI locale should win over
        course rows when both exist, so a Russian CT row is shown for RU UI
        even if the course row is still in English and ``source_locale`` is ru
        (legacy / mixed authoring)."""
        monkeypatch.setattr(
            "app.api.v1.courses.crud.translate_course_content",
            lambda *args, **kwargs: OrchestratorReport(),
        )
        course = _create_course(
            client,
            title="Placeholder",
            description="Placeholder",
        )
        cid = course["id"]
        client.put(f"{PREFIX}/{cid}", json={"status": "published"})
        row = db.get(Course, cid)
        assert row is not None
        row.title = "EN title in DB not matching RU"
        row.description = "EN desc in DB"
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=cid,
                field="title",
                locale="ru",
                text="Правильный RU title",
                source_hash="h1",
                status="ok",
                origin="mt",
            )
        )
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=cid,
                field="description",
                locale="ru",
                text="Правильный RU desc",
                source_hash="h2",
                status="ok",
                origin="mt",
            )
        )
        db.commit()

        r = anon_client.get(
            PREFIX,
            headers={"Accept-Language": "ru"},
        )
        assert r.status_code == 200
        c = next(c for c in r.json() if c["id"] == cid)
        assert c["title"] == "Правильный RU title"
        assert c["description"] == "Правильный RU desc"
