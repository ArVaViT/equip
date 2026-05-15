import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_optional_user
from app.main import app
from app.models.assignment import Assignment
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from tests.conftest import STUDENT_ID, TEACHER_ID

OTHER_TEACHER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _ensure_enrolled_student_row(db: Session) -> None:
    """Enrollment FK requires a profiles row; ``client`` only seeds the teacher."""
    if db.query(User).filter(User.id == STUDENT_ID).first():
        return
    db.add(
        User(
            id=STUDENT_ID,
            email="student@example.com",
            full_name="Test Student",
            role=UserRole.STUDENT.value,
        )
    )
    db.flush()


def _seed_course_graph(db: Session) -> tuple[Course, Module, Chapter]:
    _ensure_enrolled_student_row(db)
    course = Course(
        id="course-progress",
        title="Progress Course",
        description="Regression test course",
        status="published",
        created_by=TEACHER_ID,
    )
    module = Module(
        id="module-progress",
        course_id=course.id,
        title="Module 1",
        order_index=1,
    )
    chapter = Chapter(
        id="chapter-progress",
        module_id=module.id,
        title="Chapter 1",
        order_index=1,
        chapter_type="assignment",
    )
    enrollment = Enrollment(
        id="enroll-progress",
        user_id=STUDENT_ID,
        course_id=course.id,
        progress=0,
    )
    db.add_all([course, module, chapter, enrollment])
    db.commit()
    return course, module, chapter


def _seed_foreign_teacher_chapter(db: Session) -> Chapter:
    if not db.query(User).filter(User.id == OTHER_TEACHER_ID).first():
        db.add(
            User(
                id=OTHER_TEACHER_ID,
                email="foreign-teacher@example.com",
                full_name="Foreign",
                role=UserRole.TEACHER.value,
            )
        )
        db.flush()
    course = Course(
        id="course-foreign-asg",
        title="Foreign",
        description="x",
        status="published",
        created_by=OTHER_TEACHER_ID,
        quiz_weight=30,
        assignment_weight=50,
        participation_weight=20,
    )
    module = Module(
        id="mod-foreign-asg",
        course_id=course.id,
        title="M",
        order_index=1,
    )
    chapter = Chapter(
        id="chapter-foreign-asg",
        module_id=module.id,
        title="Foreign chapter",
        order_index=1,
        chapter_type="assignment",
    )
    db.add_all([course, module, chapter])
    db.commit()
    return chapter


class TestListChapterAssignments:
    """GET /api/v1/assignments/chapter/{chapter_id}"""

    def test_teacher_lists_assignments(self, client: TestClient, db: Session):
        _course, _mod, chapter = _seed_course_graph(db)
        r = client.post(
            "/api/v1/assignments",
            json={
                "chapter_id": chapter.id,
                "title": "Task A",
                "description": "Do it",
                "max_score": 50,
            },
        )
        assert r.status_code == 201, r.text
        r2 = client.get(f"/api/v1/assignments/chapter/{chapter.id}")
        assert r2.status_code == 200, r2.text
        items = r2.json()
        assert len(items) == 1
        assert items[0]["title"] == "Task A"
        assert items[0]["max_score"] == 50

    def test_enrolled_student_can_list(self, student_client: TestClient, db: Session):
        _course, _mod, chapter = _seed_course_graph(db)
        r = student_client.get(f"/api/v1/assignments/chapter/{chapter.id}")
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_not_enrolled_forbidden(self, student_client: TestClient, db: Session):
        foreign = _seed_foreign_teacher_chapter(db)
        r = student_client.get(f"/api/v1/assignments/chapter/{foreign.id}")
        assert r.status_code == 403


class TestCreateAssignment:
    """POST /api/v1/assignments"""

    def test_happy_path(self, client: TestClient, db: Session):
        _course, _mod, chapter = _seed_course_graph(db)
        r = client.post(
            "/api/v1/assignments",
            json={
                "chapter_id": chapter.id,
                "title": "New homework",
                "description": "Details",
                "max_score": 25,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["chapter_id"] == chapter.id
        assert body["title"] == "New homework"
        assert body["max_score"] == 25
        assert "id" in body

    def test_not_chapter_owner(self, client: TestClient, db: Session):
        foreign = _seed_foreign_teacher_chapter(db)
        r = client.post(
            "/api/v1/assignments",
            json={"chapter_id": foreign.id, "title": "Hack", "max_score": 10},
        )
        assert r.status_code == 403

    def test_student_forbidden(self, student_client: TestClient, db: Session):
        _course, _mod, chapter = _seed_course_graph(db)
        r = student_client.post(
            "/api/v1/assignments",
            json={"chapter_id": chapter.id, "title": "No", "max_score": 10},
        )
        assert r.status_code == 403


class TestUpdateAssignment:
    """PUT /api/v1/assignments/{assignment_id}"""

    def test_happy_path(self, client: TestClient, db: Session):
        _course, _mod, chapter = _seed_course_graph(db)
        create = client.post(
            "/api/v1/assignments",
            json={"chapter_id": chapter.id, "title": "Old", "max_score": 10},
        )
        assert create.status_code == 201
        aid = create.json()["id"]
        r = client.put(
            f"/api/v1/assignments/{aid}",
            json={"title": "Updated", "max_score": 20},
        )
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Updated"
        assert r.json()["max_score"] == 20

    def test_not_found(self, client: TestClient, db: Session):
        r = client.put(
            f"/api/v1/assignments/{uuid.uuid4()}",
            json={"title": "Nope"},
        )
        assert r.status_code == 404

    def test_not_chapter_owner(self, client: TestClient, db: Session):
        foreign = _seed_foreign_teacher_chapter(db)
        asg = Assignment(
            id=uuid.uuid4(),
            chapter_id=foreign.id,
            title="Other",
            max_score=10,
        )
        db.add(asg)
        db.commit()
        r = client.put(
            f"/api/v1/assignments/{asg.id}",
            json={"title": "Stolen"},
        )
        assert r.status_code == 403


class TestDeleteAssignment:
    """DELETE /api/v1/assignments/{assignment_id}"""

    def test_happy_path(self, client: TestClient, db: Session):
        _course, _mod, chapter = _seed_course_graph(db)
        create = client.post(
            "/api/v1/assignments",
            json={"chapter_id": chapter.id, "title": "Tmp", "max_score": 10},
        )
        aid = create.json()["id"]
        r = client.delete(f"/api/v1/assignments/{aid}")
        assert r.status_code == 204
        listed = client.get(f"/api/v1/assignments/chapter/{chapter.id}")
        assert listed.json() == []

    def test_not_found(self, client: TestClient, db: Session):
        r = client.delete(f"/api/v1/assignments/{uuid.uuid4()}")
        assert r.status_code == 404


class TestListAssignmentSubmissions:
    """GET /api/v1/assignments/{assignment_id}/submissions"""

    def test_teacher_lists_submissions(
        self,
        client: TestClient,
        student_client: TestClient,
        db: Session,
        teacher: User,
    ):
        _course, _mod, chapter = _seed_course_graph(db)
        aid = uuid.uuid4()
        db.add(
            Assignment(
                id=aid,
                chapter_id=chapter.id,
                title="Sub test",
                max_score=10,
            )
        )
        db.commit()
        sub = student_client.post(
            f"/api/v1/assignments/{aid}/submit",
            json={"content": "Here"},
        )
        assert sub.status_code == 201, sub.text
        app.dependency_overrides[get_current_user] = lambda: teacher
        app.dependency_overrides[get_optional_user] = lambda: teacher
        r = client.get(f"/api/v1/assignments/{aid}/submissions")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["content"] == "Here"

    def test_not_found(self, client: TestClient, db: Session):
        r = client.get(f"/api/v1/assignments/{uuid.uuid4()}/submissions")
        assert r.status_code == 404

    def test_student_forbidden(self, student_client: TestClient, db: Session):
        _course, _mod, chapter = _seed_course_graph(db)
        aid = uuid.uuid4()
        db.add(Assignment(id=aid, chapter_id=chapter.id, title="T", max_score=10))
        db.commit()
        r = student_client.get(f"/api/v1/assignments/{aid}/submissions")
        assert r.status_code == 403


class TestGradeSubmission:
    """PUT /api/v1/assignments/submissions/{submission_id}/grade"""

    def test_happy_path(
        self,
        client: TestClient,
        student_client: TestClient,
        db: Session,
        teacher: User,
    ):
        _course, _mod, chapter = _seed_course_graph(db)
        aid = uuid.uuid4()
        db.add(
            Assignment(
                id=aid,
                chapter_id=chapter.id,
                title="Grade me",
                max_score=10,
            )
        )
        db.commit()
        sub_resp = student_client.post(
            f"/api/v1/assignments/{aid}/submit",
            json={"content": "Answer"},
        )
        assert sub_resp.status_code == 201
        sid = sub_resp.json()["id"]
        app.dependency_overrides[get_current_user] = lambda: teacher
        app.dependency_overrides[get_optional_user] = lambda: teacher
        r = client.put(
            f"/api/v1/assignments/submissions/{sid}/grade",
            json={"grade": 8, "feedback": "Nice", "status": "graded"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["grade"] == 8
        assert body["feedback"] == "Nice"
        assert body["status"] == "graded"

    def test_grade_exceeds_max_score(
        self,
        client: TestClient,
        student_client: TestClient,
        db: Session,
        teacher: User,
    ):
        _course, _mod, chapter = _seed_course_graph(db)
        aid = uuid.uuid4()
        db.add(Assignment(id=aid, chapter_id=chapter.id, title="Cap", max_score=10))
        db.commit()
        sub_resp = student_client.post(
            f"/api/v1/assignments/{aid}/submit",
            json={"content": "x"},
        )
        sid = sub_resp.json()["id"]
        app.dependency_overrides[get_current_user] = lambda: teacher
        app.dependency_overrides[get_optional_user] = lambda: teacher
        r = client.put(
            f"/api/v1/assignments/submissions/{sid}/grade",
            json={"grade": 11, "status": "graded"},
        )
        assert r.status_code == 422

    def test_submission_not_found(self, client: TestClient, db: Session):
        r = client.put(
            f"/api/v1/assignments/submissions/{uuid.uuid4()}/grade",
            json={"grade": 5, "status": "graded"},
        )
        assert r.status_code == 404


def test_my_progress_returns_only_completed_course_chapters(student_client: TestClient, db: Session):
    course, _module, chapter = _seed_course_graph(db)
    other_course = Course(
        id="other-course",
        title="Other Course",
        description="Should not leak into progress response",
        status="published",
        created_by=TEACHER_ID,
    )
    other_module = Module(
        id="other-module",
        course_id=other_course.id,
        title="Other Module",
        order_index=1,
    )
    other_chapter = Chapter(
        id="other-chapter",
        module_id=other_module.id,
        title="Other Chapter",
        order_index=1,
    )
    db.add_all([other_course, other_module, other_chapter])
    db.commit()
    db.add_all(
        [
            ChapterProgress(user_id=STUDENT_ID, chapter_id=chapter.id, completed=True, completion_type="self"),
            ChapterProgress(user_id=STUDENT_ID, chapter_id=other_chapter.id, completed=True, completion_type="self"),
        ]
    )
    db.commit()

    response = student_client.get(f"/api/v1/progress/course/{course.id}/my-progress")

    assert response.status_code == 200, response.text
    assert response.json() == [chapter.id]


def test_submit_assignment_survives_concurrent_chapter_progress_insert(student_client: TestClient, db: Session):
    """The submit handler races a teacher manually marking the chapter
    complete: both can hit the ``uq_progress_user_chapter`` unique key
    at commit. Before the SAVEPOINT fix the entire submit transaction
    rolled back and the ``AssignmentSubmission`` was lost.

    Reproduces the race by pre-inserting a competing ChapterProgress
    row (so the unique key is already taken) and forcing the handler's
    initial ChapterProgress lookup to MISS so it falls into the INSERT
    path. In production the lookup miss would happen because the
    competing writer hasn't committed yet; in test we patch ``.first()``
    once.
    """
    from sqlalchemy.orm import Query

    _course, _module, chapter = _seed_course_graph(db)
    assignment = Assignment(
        id=uuid.uuid4(),
        chapter_id=chapter.id,
        title="Reflection",
        max_score=10,
    )
    db.add(assignment)
    db.add(
        ChapterProgress(
            user_id=STUDENT_ID,
            chapter_id=chapter.id,
            completed=True,
            completion_type="teacher",
        )
    )
    db.commit()

    real_first = Query.first
    state = {"missed": False}

    def _maybe_miss(self):
        descs = self.column_descriptions
        if not state["missed"] and descs and getattr(descs[0].get("type"), "__name__", "") == "ChapterProgress":
            state["missed"] = True
            return None
        return real_first(self)

    Query.first = _maybe_miss
    try:
        resp = student_client.post(
            f"/api/v1/assignments/{assignment.id}/submit",
            json={"content": "x"},
        )
    finally:
        Query.first = real_first

    # Before the fix this came back as 409 (IntegrityError middleware);
    # after, the SAVEPOINT absorbs the collision and the submit commits.
    assert resp.status_code == 201, resp.text

    db.expire_all()
    progress_rows = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.user_id == STUDENT_ID,
            ChapterProgress.chapter_id == chapter.id,
        )
        .all()
    )
    assert len(progress_rows) == 1
    assert progress_rows[0].completed is True

    from app.models.assignment import AssignmentSubmission

    sub_count = db.query(AssignmentSubmission).filter(AssignmentSubmission.assignment_id == assignment.id).count()
    assert sub_count == 1


def test_student_can_fetch_own_assignment_submissions(student_client: TestClient, db: Session):
    course, _module, chapter = _seed_course_graph(db)
    assignment = Assignment(
        id=uuid.uuid4(),
        chapter_id=chapter.id,
        title="Reflection",
        description="Write a reflection",
        max_score=10,
    )
    db.add(assignment)
    db.commit()

    submit_response = student_client.post(
        f"/api/v1/assignments/{assignment.id}/submit",
        json={"content": "My submission"},
    )
    assert submit_response.status_code == 201, submit_response.text

    my_submissions_response = student_client.get(f"/api/v1/assignments/{assignment.id}/my-submissions")

    assert my_submissions_response.status_code == 200, my_submissions_response.text
    body = my_submissions_response.json()
    assert len(body) == 1
    assert body[0]["content"] == "My submission"
    assert body[0]["student_id"] == str(STUDENT_ID)

    progress = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.user_id == STUDENT_ID,
            ChapterProgress.chapter_id == chapter.id,
        )
        .first()
    )
    assert progress is not None
    assert progress.completed is True

    db.expire_all()
    enrollment = (
        db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == course.id).first()
    )
    assert enrollment is not None
    assert enrollment.progress == 100


def test_content_chapter_does_not_affect_progress(student_client: TestClient, db: Session):
    """Content-only chapters (reading, video, etc.) should not count toward progress."""
    course, _module, _chapter = _seed_course_graph(db)

    content_chapter = Chapter(
        id="chapter-content",
        module_id=_module.id,
        title="Reading Material",
        order_index=2,
        chapter_type="reading",
    )
    db.add(content_chapter)
    db.commit()

    enrollment = (
        db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == course.id).first()
    )
    assert enrollment is not None
    assert enrollment.progress == 0

    db.add(
        ChapterProgress(
            user_id=STUDENT_ID,
            chapter_id=_chapter.id,
            completed=True,
            completion_type="quiz",
        )
    )
    db.commit()

    from app.services.course_service import sync_enrollment_progress

    sync_enrollment_progress(db, STUDENT_ID, course.id)
    db.commit()
    db.refresh(enrollment)
    assert enrollment.progress == 100
