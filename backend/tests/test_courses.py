"""Tests for the /api/v1/courses endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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

    def test_course_limit_blocks_teacher_but_not_admin(
        self, client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
    ):
        """Anti-abuse cap: live courses per teacher are limited; admins and
        trash-then-create flows are not."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "MAX_COURSES_PER_TEACHER", 2)
        _create_course(client, title="One")
        second = _create_course(client, title="Two")

        resp = client.post(PREFIX, json={"title": "Three"})
        assert resp.status_code == 400
        assert "limit" in resp.json()["detail"]["message"].lower()

        # Soft-deleting frees a slot - deleted courses must not count.
        del_resp = client.delete(f"{PREFIX}/{second['id']}")
        assert del_resp.status_code in (200, 204)
        _create_course(client, title="Three (after trash)")

        # Admins are exempt from the cap.
        from app.models.user import User, UserRole

        teacher = db.query(User).filter(User.id == TEACHER_ID).first()
        teacher.role = UserRole.ADMIN.value
        db.commit()
        _create_course(client, title="Admin Four")
        _create_course(client, title="Admin Five")

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

    def test_owner_teacher_cannot_set_access_mode(self, client: TestClient):
        """``access_mode`` gates public vs institute enrollment (ADR-010) and
        is admin-only — even the course's own teacher-owner is forbidden from
        flipping it, since that would let them self-promote an institute
        course to public."""
        course = _create_course(client)
        resp = client.put(
            f"{PREFIX}/{course['id']}",
            json={"access_mode": "public"},
        )
        assert resp.status_code == 403


class TestAdminManagesForeignCourse:
    """Admin-bypass unification: the whole content tree (course CRUD,
    modules, chapters) accepts admin as well as the owner, matching
    blocks/quizzes/assignments. Certificate teacher-approval remains
    deliberately owner-only (two-stage approval)."""

    def test_admin_updates_foreign_course(self, admin_client: TestClient, client: TestClient):
        course = _create_course(client)
        resp = admin_client.put(f"{PREFIX}/{course['id']}", json={"title": "Admin Edit"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == "Admin Edit"

    def test_admin_deletes_and_restores_foreign_course(self, admin_client: TestClient, client: TestClient):
        course = _create_course(client)
        resp = admin_client.delete(f"{PREFIX}/{course['id']}")
        assert resp.status_code == 204, resp.text
        resp = admin_client.post(f"{PREFIX}/{course['id']}/restore")
        assert resp.status_code == 200, resp.text

    def test_admin_manages_foreign_modules_and_chapters(self, admin_client: TestClient, client: TestClient):
        course = _create_course(client)
        created = admin_client.post(f"{PREFIX}/{course['id']}/modules", json={"title": "Admin Module"})
        assert created.status_code == 201, created.text
        module_id = created.json()["id"]

        updated = admin_client.put(f"{PREFIX}/{course['id']}/modules/{module_id}", json={"title": "Renamed"})
        assert updated.status_code == 200, updated.text

        chapter = admin_client.post(
            f"{PREFIX}/{course['id']}/modules/{module_id}/chapters",
            json={"title": "Admin Chapter"},
        )
        assert chapter.status_code == 201, chapter.text
        chapter_id = chapter.json()["id"]

        resp = admin_client.delete(f"{PREFIX}/{course['id']}/modules/{module_id}/chapters/{chapter_id}")
        assert resp.status_code == 204, resp.text

        resp = admin_client.delete(f"{PREFIX}/{course['id']}/modules/{module_id}")
        assert resp.status_code == 204, resp.text

    def test_other_teacher_still_forbidden(self, db: Session, client: TestClient):
        """Unifying admin access must not loosen the teacher boundary."""
        from app.api.dependencies import get_current_user, get_optional_user
        from app.main import app
        from app.models.user import User, UserRole

        course = _create_course(client)
        other = User(
            id="dddddddd-dddd-dddd-dddd-dddddddddddd",
            email="other-teacher@example.com",
            full_name="Other Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(other)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: other
        app.dependency_overrides[get_optional_user] = lambda: other
        resp = client.put(f"{PREFIX}/{course['id']}", json={"title": "Steal"})
        assert resp.status_code == 403, resp.text


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

    def test_clone_carries_the_grading_configuration(self, client: TestClient, db: Session):
        """Cloning is how a school reopens a course for a new cohort (D13).

        Dropping the grading config would hand the copy platform defaults: a
        course graded «letter, pass at 80» would quietly become «pass at 70»,
        and tuned weights would reset — with nobody told, in the one workflow
        where the teacher expects an exact copy.
        """
        from app.models.course import Course

        course = _create_course(client, title="Graded Original")
        original = db.query(Course).filter(Course.id == course["id"]).first()
        original.grading_scheme = "five_point"
        original.pass_threshold = 65
        original.quiz_weight = 70
        original.assignment_weight = 30
        original.academic_hours = 36
        db.commit()

        clone_id = client.post(f"{PREFIX}/{course['id']}/clone").json()["id"]
        clone = db.query(Course).filter(Course.id == clone_id).first()

        assert clone.grading_scheme == "five_point"
        assert float(clone.pass_threshold) == 65.0
        assert (clone.quiz_weight, clone.assignment_weight) == (70, 30)
        assert clone.academic_hours == 36

    def test_clone_nonexistent_returns_404(self, client: TestClient):
        resp = client.post(f"{PREFIX}/nonexistent-id/clone")
        assert resp.status_code == 404

    def test_clone_draft_by_non_owner_forbidden(self, db: Session, client: TestClient):
        """Drafts are only visible to their owner, so cloning one is too —
        regardless of the requester's teacher role."""
        import uuid

        from app.api.dependencies import get_current_user, get_optional_user
        from app.main import app
        from app.models.user import User, UserRole

        course = _create_course(client)  # created as "draft" by default
        other = User(
            id=uuid.uuid4(),
            email="other-cloner@example.com",
            full_name="Other Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(other)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: other
        app.dependency_overrides[get_optional_user] = lambda: other
        resp = client.post(f"{PREFIX}/{course['id']}/clone")
        assert resp.status_code == 403

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

    def test_clone_copies_cv_text_rows_so_clone_is_not_empty(self, client: TestClient):
        """Phase 5z regression: the clone path used to copy only structural
        rows; cv text rows were left untouched. Result: every cloned
        title / description / content / question_text / option_text came
        back empty even though the entities existed. Now the clone
        duplicates cv rows per entity_type so the new course is a real
        forkable copy, not an empty shell."""
        course = _create_course(client, title="Bilingual Source", description="Some description text")
        mod_resp = client.post(
            f"{PREFIX}/{course['id']}/modules",
            json={"title": "M1 Title", "order_index": 1, "description": "M1 description"},
        )
        module_id = mod_resp.json()["id"]
        client.post(
            f"{PREFIX}/{course['id']}/modules/{module_id}/chapters",
            json={"title": "Chapter One", "chapter_type": "reading", "order_index": 1},
        )

        clone_resp = client.post(f"{PREFIX}/{course['id']}/clone")
        clone = clone_resp.json()
        # Course title surfaces with " (Copy)" appended.
        assert clone["title"].endswith("(Copy)")
        assert clone["description"] == "Some description text"
        # Module text round-trips intact, NOT empty.
        cloned_module = clone["modules"][0]
        assert cloned_module["title"] == "M1 Title"
        assert cloned_module["description"] == "M1 description"
        # Chapter title (still a spine column) carries through.
        assert cloned_module["chapters"][0]["title"] == "Chapter One"


# ---------------------------------------------------------------------------
# Localized catalog (content_translations read path)
# ---------------------------------------------------------------------------


class TestCatalogLocalizedMetadata:
    def _seed_en_translations(self, db: Session, course_id: str) -> None:
        from app.services.content_versions.write import record_mt_version

        record_mt_version(
            db,
            entity_type="course",
            entity_id=course_id,
            field="title",
            locale="en",
            text="English catalog title",
            source_locale="ru",
            source_hash="testhash",
        )
        record_mt_version(
            db,
            entity_type="course",
            entity_id=course_id,
            field="description",
            locale="en",
            text="English catalog description",
            source_locale="ru",
            source_hash="testhash2",
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
            "app.services.translation.pipeline_hooks.translate_course_content",
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
            "app.services.translation.pipeline_hooks.translate_course_content",
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
            "app.services.translation.pipeline_hooks.translate_course_content",
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

    def test_localized_detail_includes_full_module_chapter_tree(
        self,
        client: TestClient,
        db: Session,
        anon_client: TestClient,
    ) -> None:
        """The localized course-detail builder must carry the WHOLE module +
        chapter tree with every field, in order. Guards the single-pass
        bottom-up construction in ``build_localized_course_response_with_tree``
        against silently dropping a chapter/module field (the field lists are
        hand-written there for performance, so this is their parity net)."""
        from app.models.course import Chapter
        from tests._cv_helpers import _seed_text_row, make_module_with_text

        course = _create_course(client, title="Tree Course", description="Tree desc")
        cid = course["id"]
        module = make_module_with_text(db, course_id=cid, title="Module One", order_index=0, locale="en")
        ch1 = Chapter(
            id=f"{cid}-c1",
            module_id=module.id,
            title="Chapter One",
            order_index=0,
            chapter_type="quiz",
            requires_completion=True,
            is_locked=False,
        )
        ch2 = Chapter(
            id=f"{cid}-c2",
            module_id=module.id,
            title="Chapter Two",
            order_index=1,
            chapter_type="reading",
            requires_completion=False,
            is_locked=True,
        )
        db.add_all([ch1, ch2])
        db.flush()
        _seed_text_row(db, entity_type="chapter", entity_id=ch1.id, field="title", locale="en", text="Chapter One")
        _seed_text_row(db, entity_type="chapter", entity_id=ch2.id, field="title", locale="en", text="Chapter Two")
        db.commit()
        client.put(f"{PREFIX}/{cid}", json={"status": "published"})

        r = anon_client.get(f"{PREFIX}/{cid}", headers={"Accept-Language": "en"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["title"] == "Tree Course"
        assert body["status"] == "published"
        assert len(body["modules"]) == 1
        mod = body["modules"][0]
        assert mod["title"] == "Module One"
        assert mod["course_id"] == cid
        chapters = mod["chapters"]
        # Order preserved (Module.chapters order_by order_index).
        assert [c["title"] for c in chapters] == ["Chapter One", "Chapter Two"]
        c1 = chapters[0]
        assert c1["id"] == f"{cid}-c1"
        assert c1["module_id"] == module.id
        assert c1["chapter_type"] == "quiz"
        assert c1["requires_completion"] is True
        assert c1["is_locked"] is False
        assert chapters[1]["is_locked"] is True
        assert chapters[1]["chapter_type"] == "reading"

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
            "app.services.translation.pipeline_hooks.translate_course_content",
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
            "app.services.translation.pipeline_hooks.translate_course_content",
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
            "app.services.translation.pipeline_hooks.translate_course_content",
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

        from app.services.content_versions.write import record_mt_version

        record_mt_version(
            db,
            entity_type="module",
            entity_id=str(mod_id),
            field="title",
            locale="en",
            text="Module title EN",
            source_locale="ru",
            source_hash="m1",
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
        """``content_versions`` for the active UI locale should win over the
        source-locale row when both exist, so a Russian RU row is shown for
        RU UI even when the source row carries English text (legacy / mixed
        authoring).

        Phase 5g: ``courses.title|description`` columns are gone. The
        "source" here is the EN cv row laid down by ``_create_course``;
        the overlay is the RU MT row added below. The previous
        ``row.title = ...`` runtime-attribute writes were dead under
        the new architecture (no column to persist to) and have been
        removed so the test only mutates state that actually exists.
        """
        monkeypatch.setattr(
            "app.services.translation.pipeline_hooks.translate_course_content",
            lambda *args, **kwargs: OrchestratorReport(),
        )
        course = _create_course(
            client,
            title="Placeholder",
            description="Placeholder",
        )
        cid = course["id"]
        client.put(f"{PREFIX}/{cid}", json={"status": "published"})
        from app.services.content_versions.write import record_mt_version

        record_mt_version(
            db,
            entity_type="course",
            entity_id=cid,
            field="title",
            locale="ru",
            text="Правильный RU title",
            source_locale="en",
            source_hash="h1",
        )
        record_mt_version(
            db,
            entity_type="course",
            entity_id=cid,
            field="description",
            locale="ru",
            text="Правильный RU desc",
            source_locale="en",
            source_hash="h2",
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
