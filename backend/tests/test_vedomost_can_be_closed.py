"""«Закрытие ведомости» — turning a live report into a signed document (D11).

A report is live; a document is not. Everything a sheet is computed from stays
editable after it is signed: a teacher can re-mark an essay, lift an exemption,
or hand-set a grade months later. A printable rendered from live data would
change in the filing cabinet.

So most of what is worth testing here is not "does it compute the right
result" but "does the result stay put while the world moves underneath it".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.cohort import Cohort
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.grade_sheet import GradeSheet, GradeSheetRow
from app.models.org_settings import OrgSettings
from app.models.quiz import Quiz, QuizAttempt
from app.models.student_grade import StudentGrade
from app.models.user import User
from tests.conftest import TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID

SHEET_URL = "/api/v1/grades/course/{course_id}/sheet"


def _course(db: Session, teacher, course_id: str, *, threshold: str = "70.00"):
    course = Course(
        id=course_id,
        status="published",
        created_by=teacher.id,
        quiz_weight=100,
        assignment_weight=0,
        grading_scheme="letter",
        pass_threshold=Decimal(threshold),
    )
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"{course_id}-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.commit()
    return course, quiz


def _enrol(db: Session, course_id: str, student_id, *, cohort_id=None, progress: int = 100) -> None:
    db.add(
        Enrollment(
            id=f"enr-{course_id}-{student_id}",
            user_id=student_id,
            course_id=course_id,
            cohort_id=cohort_id,
            progress=progress,
        )
    )


def _attempt(db: Session, quiz, student_id, score: int) -> None:
    db.add(
        QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=student_id,
            score=score,
            max_score=100,
            passed=score >= 70,
            completed_at=datetime.now(UTC),
        )
    )


# --------------------------------------------------------------------------
# the result recorded
# --------------------------------------------------------------------------


def test_closing_records_pass_and_fail_against_the_line(admin_client, db: Session, teacher, student) -> None:
    course, quiz = _course(db, teacher, "c-sheet-passfail")
    failing = User(id=uuid.uuid4(), email="failing@example.com", full_name="Борис", role="student")
    db.add(failing)
    db.flush()
    _enrol(db, course.id, STUDENT_ID)
    _enrol(db, course.id, failing.id)
    _attempt(db, quiz, STUDENT_ID, 90)
    _attempt(db, quiz, failing.id, 40)
    db.commit()

    resp = admin_client.post(SHEET_URL.format(course_id=course.id))

    assert resp.status_code == 201, resp.text
    by_student = {r["student_id"]: r for r in resp.json()["rows"]}
    assert by_student[str(STUDENT_ID)]["result_state"] == "pass"
    assert by_student[str(STUDENT_ID)]["official_code"] == "A"
    assert by_student[str(failing.id)]["result_state"] == "fail"


def test_a_hand_set_grade_decides_the_line_and_is_marked(admin_client, db: Session, teacher, student) -> None:
    """The override IS the official grade (D7). A code is measured by its
    band's floor, because an override stores a symbol and the line is a number
    — and a signing director sees at a glance that it was set by hand."""
    course, quiz = _course(db, teacher, "c-sheet-override")
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 10)
    db.add(StudentGrade(course_id=course.id, student_id=STUDENT_ID, override_code="B"))
    db.commit()

    row = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "pass", "«B» floors at 80, above the 70 line"
    assert row["official_code"] == "B"
    assert row["is_override"] is True


def test_a_student_excused_from_everything_is_not_attested(admin_client, db: Session, teacher, student) -> None:
    """Neither a pass nor a failure. Calling it either would put a verdict on a
    page where a person still has to make one."""
    from app.services.grade_exemption_service import apply_exemption

    course, quiz = _course(db, teacher, "c-sheet-notattested")
    _enrol(db, course.id, STUDENT_ID)
    db.commit()
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="quiz",
        item_id=quiz.id,
        teacher_id=teacher.id,
    )
    db.commit()

    row = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "not_attested"
    assert row["official_code"] is None


def test_a_course_with_nothing_gradable_passes_by_completion(admin_client, db: Session, teacher, student) -> None:
    course = Course(id="c-sheet-completion", status="published", created_by=teacher.id)
    db.add(course)
    _enrol(db, course.id, STUDENT_ID)
    db.commit()

    row = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "completion_pass"


def test_an_unmarked_class_is_not_recorded_as_failing(admin_client, db: Session, teacher, student) -> None:
    """Nothing has been marked, so there is no result — and a document must not
    invent one. Recording «fail» here would fail a whole class on paper for
    work nobody had looked at."""
    course, _quiz = _course(db, teacher, "c-sheet-unmarked")
    _enrol(db, course.id, STUDENT_ID)
    db.commit()

    row = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "not_attested"


# --------------------------------------------------------------------------
# the document does not move
# --------------------------------------------------------------------------


def test_a_closed_sheet_survives_a_regrade(admin_client, db: Session, teacher, student) -> None:
    course, quiz = _course(db, teacher, "c-sheet-frozen")
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 95)
    db.commit()
    admin_client.post(SHEET_URL.format(course_id=course.id))

    attempt = db.query(QuizAttempt).filter(QuizAttempt.user_id == STUDENT_ID).first()
    attempt.score = 5
    db.commit()

    row = admin_client.get(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "pass"
    assert row["official_code"] == "A", "the paper in the folder still says what it said"


def test_a_closed_sheet_survives_the_school_moving_its_bands(admin_client, db: Session, teacher, student) -> None:
    course, quiz = _course(db, teacher, "c-sheet-bands")
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 91)
    db.commit()
    admin_client.post(SHEET_URL.format(course_id=course.id))

    settings = db.query(OrgSettings).first()
    settings.grade_bands = {"letter": [[95, "A"], [85, "B"], [75, "C"], [65, "D"], [0, "F"]]}
    db.commit()

    row = admin_client.get(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["official_code"] == "A"


def test_reclosing_supersedes_rather_than_overwrites(admin_client, db: Session, teacher, student) -> None:
    """The history of what was signed survives a correction."""
    course, quiz = _course(db, teacher, "c-sheet-supersede")
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 95)
    db.commit()
    first = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["id"]

    attempt = db.query(QuizAttempt).filter(QuizAttempt.user_id == STUDENT_ID).first()
    attempt.score = 40
    db.commit()
    second = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["id"]

    assert first != second
    assert db.query(GradeSheet).count() == 2, "the old sheet is kept"
    old = db.query(GradeSheet).filter(GradeSheet.id == uuid.UUID(first)).first()
    assert old.superseded_at is not None
    assert db.query(GradeSheetRow).filter(GradeSheetRow.sheet_id == old.id).first().result_state == "pass"


def test_reopening_needs_a_reason_and_is_written_down(admin_client, db: Session, teacher, student) -> None:
    """A signed document cannot be quietly corrected."""
    from app.models.audit_log import AuditLog

    course, quiz = _course(db, teacher, "c-sheet-reopen")
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 95)
    db.commit()
    sheet_id = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["id"]

    refused = admin_client.post(f"/api/v1/grades/sheet/{sheet_id}/reopen", json={"reason": ""})
    assert refused.status_code == 422, "a reopening with no reason is what the reason exists to stop"

    resp = admin_client.post(f"/api/v1/grades/sheet/{sheet_id}/reopen", json={"reason": "Апелляция студента"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["reopened_at"] is not None
    assert resp.json()["reopen_reason"] == "Апелляция студента"
    entry = db.query(AuditLog).filter(AuditLog.action == "grade_sheet_reopened").first()
    assert entry is not None


# --------------------------------------------------------------------------
# who belongs on the page
# --------------------------------------------------------------------------


def test_a_sheet_holds_one_cohort_only(admin_client, db: Session, teacher, student) -> None:
    """The moment a school runs the same course a second year, an unscoped
    sheet mixes two поток onto one signed page and nothing afterwards can tell
    them apart (D11)."""
    course, _quiz = _course(db, teacher, "c-sheet-cohorts")
    first_year = Cohort(
        id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        status="active",
    )
    db.add(first_year)
    db.flush()
    other = User(id=uuid.uuid4(), email="other@example.com", full_name="Другой", role="student")
    db.add(other)
    db.flush()
    _enrol(db, course.id, STUDENT_ID, cohort_id=first_year.id)
    _enrol(db, course.id, other.id)
    db.commit()

    scoped = admin_client.post(f"{SHEET_URL.format(course_id=course.id)}?cohort_id={first_year.id}")

    assert scoped.status_code == 201
    assert [r["student_id"] for r in scoped.json()["rows"]] == [str(STUDENT_ID)]


def test_the_no_cohort_bucket_is_its_own_sheet(admin_client, db: Session, teacher, student) -> None:
    """`cohort_id IS NULL` is «без потока» — a real bucket for solo students,
    not "everyone"."""
    course, _quiz = _course(db, teacher, "c-sheet-nocohort")
    cohort = Cohort(
        id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        status="active",
    )
    db.add(cohort)
    db.flush()
    in_cohort = User(id=uuid.uuid4(), email="incohort@example.com", full_name="Вкогорте", role="student")
    db.add(in_cohort)
    db.flush()
    _enrol(db, course.id, STUDENT_ID)
    _enrol(db, course.id, in_cohort.id, cohort_id=cohort.id)
    db.commit()

    rows = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"]

    assert [r["student_id"] for r in rows] == [str(STUDENT_ID)]


def test_a_teacher_cannot_close_a_sheet(client, db: Session, teacher, student) -> None:
    """Closing is what turns a report into a document someone signs — a
    director's action, like the scheme itself."""
    course, _quiz = _course(db, teacher, "c-sheet-teacher")
    _enrol(db, course.id, STUDENT_ID)
    db.commit()

    resp = client.post(SHEET_URL.format(course_id=course.id))

    assert resp.status_code == 403
    assert db.query(GradeSheet).count() == 0


def test_a_teacher_can_read_the_sheet(client, db: Session, teacher, student) -> None:
    """They have to be able to show it to the student it is about."""
    course, _quiz = _course(db, teacher, "c-sheet-teacher-read")
    _enrol(db, course.id, STUDENT_ID)
    db.commit()

    resp = client.get(SHEET_URL.format(course_id=course.id))

    assert resp.status_code == 200
    assert resp.json() is None, "nothing closed yet"


# --------------------------------------------------------------------------
# Found by an adversarial pass before this ever merged. Each one is here so
# that it cannot come back.
# --------------------------------------------------------------------------


def test_a_retaking_student_gets_one_line_not_two(admin_client, db: Session, teacher, student) -> None:
    """A retake is deliberately a second enrolment, and the calculator yields a
    row per enrolment — so a returning student produced two lines with the same
    primary key and the ведомость could not be closed **at all**."""
    course, quiz = _course(db, teacher, "c-sheet-retake")
    cohort = Cohort(
        id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        status="active",
    )
    db.add(cohort)
    db.flush()
    db.add(Enrollment(id="enr-retake-solo", user_id=STUDENT_ID, course_id=course.id, progress=100))
    db.add(
        Enrollment(
            id="enr-retake-cohort",
            user_id=STUDENT_ID,
            course_id=course.id,
            cohort_id=cohort.id,
            progress=100,
        )
    )
    _attempt(db, quiz, STUDENT_ID, 90)
    db.commit()

    resp = admin_client.post(f"{SHEET_URL.format(course_id=course.id)}?cohort_id={cohort.id}")

    assert resp.status_code == 201, resp.text
    assert len(resp.json()["rows"]) == 1


def test_last_years_sheet_freezes_last_years_grade(admin_client, db: Session, teacher, student) -> None:
    """The override that counts for a ведомость is the one for **its** поток.

    Resolving "which grade is current" would stamp this year's mark onto a page
    dated two years ago.
    """
    course, _quiz = _course(db, teacher, "c-sheet-two-years")
    old = Cohort(
        id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        status="completed",
    )
    new = Cohort(
        id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        status="active",
    )
    db.add_all([old, new])
    db.flush()
    db.add(
        Enrollment(
            id="enr-old",
            user_id=STUDENT_ID,
            course_id=course.id,
            cohort_id=old.id,
            progress=100,
            enrolled_at=datetime(2024, 9, 1, tzinfo=UTC),
        )
    )
    db.add(
        Enrollment(
            id="enr-new",
            user_id=STUDENT_ID,
            course_id=course.id,
            cohort_id=new.id,
            progress=100,
            enrolled_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    db.add(StudentGrade(course_id=course.id, student_id=STUDENT_ID, cohort_id=old.id, override_code="C"))
    db.add(StudentGrade(course_id=course.id, student_id=STUDENT_ID, cohort_id=new.id, override_code="A"))
    db.commit()

    row = admin_client.post(f"{SHEET_URL.format(course_id=course.id)}?cohort_id={old.id}").json()["rows"][0]

    assert row["official_code"] == "C", "the old поток's page carries the old поток's grade"


def test_a_hand_set_grade_outranks_not_attested(admin_client, db: Session, teacher, student) -> None:
    """ "Not attested" is the state that *asks* a teacher to decide. Once they
    have, the decision has to outrank the question — the sheet was discarding
    exactly the grade the design says is required there."""
    from app.services.grade_exemption_service import apply_exemption

    course, quiz = _course(db, teacher, "c-sheet-decided")
    _enrol(db, course.id, STUDENT_ID)
    db.commit()
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="quiz",
        item_id=quiz.id,
        teacher_id=teacher.id,
    )
    db.add(StudentGrade(course_id=course.id, student_id=STUDENT_ID, override_code="B"))
    db.commit()

    row = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "pass"
    assert row["official_code"] == "B"
    assert row["is_override"] is True


def test_a_pass_fail_course_records_the_verdict_not_a_percentage(admin_client, db: Session, teacher, student) -> None:
    """«Зачёт» is every required piece of work accepted, not an average
    clearing a line (D2). The sheet used to refuse to close for this scheme,
    because the rule did not exist; now it does, and no number goes on the page.
    """
    from app.models.assignment import Assignment, AssignmentSubmission

    course = Course(id="c-sheet-zachet", status="published", created_by=teacher.id, grading_scheme="pass_fail")
    db.add(course)
    module = Module(id="c-sheet-zachet-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(
        id="c-sheet-zachet-ch",
        module_id=module.id,
        order_index=0,
        chapter_type="assignment",
        title="Работа",
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="graded",
            grade=52,
            graded_by=teacher.id,
        )
    )
    _enrol(db, course.id, STUDENT_ID, progress=100)
    db.commit()

    row = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "pass", "the work was accepted; the mark on it is not the rule"
    assert row["official_score"] is None, "no percentage goes on a pass/fail page"
    assert row["official_code"] is None


def test_a_pass_fail_course_with_work_returned_is_not_passed(admin_client, db: Session, teacher, student) -> None:
    """A high mark cannot outrank «вернуть на доработку» — that is the teacher's
    "not yet", and it is the whole difference from counting marks."""
    from app.models.assignment import Assignment, AssignmentSubmission

    course = Course(id="c-sheet-returned", status="published", created_by=teacher.id, grading_scheme="pass_fail")
    db.add(course)
    module = Module(id="c-sheet-returned-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(
        id="c-sheet-returned-ch",
        module_id=module.id,
        order_index=0,
        chapter_type="assignment",
        title="Работа",
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="returned",
            grade=95,
            graded_by=teacher.id,
        )
    )
    _enrol(db, course.id, STUDENT_ID, progress=100)
    db.commit()

    row = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "fail"


def test_the_correction_mark_lands_on_the_document_people_print(admin_client, db: Session, teacher, student) -> None:
    """The «была переоткрыта» mark was stamped on the superseded page — the
    copy nobody looks at again — while the corrected sheet came out clean."""
    course, quiz = _course(db, teacher, "c-sheet-mark")
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 95)
    db.commit()
    first = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["id"]
    admin_client.post(f"/api/v1/grades/sheet/{first}/reopen", json={"reason": "Апелляция"})

    admin_client.post(SHEET_URL.format(course_id=course.id))
    live = admin_client.get(SHEET_URL.format(course_id=course.id)).json()

    assert live["corrects_sheet_id"] == first
    assert live["correction_reason"] == "Апелляция"


def test_reopening_twice_is_refused_rather_than_overwriting_the_reason(
    admin_client, db: Session, teacher, student
) -> None:
    course, quiz = _course(db, teacher, "c-sheet-double-reopen")
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 95)
    db.commit()
    sheet_id = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["id"]
    admin_client.post(f"/api/v1/grades/sheet/{sheet_id}/reopen", json={"reason": "Первая причина"})

    second = admin_client.post(f"/api/v1/grades/sheet/{sheet_id}/reopen", json={"reason": "Вторая причина"})

    assert second.status_code == 409
    sheet = db.query(GradeSheet).filter(GradeSheet.id == uuid.UUID(sheet_id)).first()
    assert sheet.reopen_reason == "Первая причина", "the earlier record is the part worth keeping"


def test_the_sheet_keeps_the_cohort_name_it_was_signed_under(admin_client, db: Session, teacher, student) -> None:
    """Cohort names are editable and live in `content_versions`; a signed
    heading is not."""
    from app.models.content_version import ContentVersion

    course, _quiz = _course(db, teacher, "c-sheet-cohort-name")
    cohort = Cohort(
        id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        status="active",
    )
    db.add(cohort)
    db.flush()
    db.add(
        ContentVersion(
            entity_type="cohort",
            entity_id=str(cohort.id),
            field="title",
            locale="ru",
            text="Поток 2026",
            origin="human",
        )
    )
    _enrol(db, course.id, STUDENT_ID, cohort_id=cohort.id)
    db.commit()

    sheet = admin_client.post(f"{SHEET_URL.format(course_id=course.id)}?cohort_id={cohort.id}").json()

    assert sheet["cohort_name"] == "Поток 2026"


# --------------------------------------------------------------------------
# A signed page keeps its own words
#
# The first version froze the numbers and left the words live, which is half a
# snapshot and therefore not one.
# --------------------------------------------------------------------------


def test_a_student_who_changes_her_name_does_not_change_the_document(
    admin_client, db: Session, teacher, student
) -> None:
    """Read live, a marriage rewrites a page already in the filing cabinet."""
    course, quiz = _course(db, teacher, "c-sheet-maiden")
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 90)
    db.commit()
    signed_as = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]["student_name"]
    # Without this the test compares None to None and passes while the snapshot
    # does nothing at all — which is exactly what it did on the first attempt.
    assert signed_as, "the document has to carry a name before it can keep one"

    person = db.query(User).filter(User.id == STUDENT_ID).first()
    person.full_name = "Новая Фамилия"
    db.commit()

    row = admin_client.get(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["student_name"] == signed_as
    assert row["student_name"] != "Новая Фамилия"


def test_the_cohort_name_comes_from_the_documents_own_language(admin_client, db: Session, teacher, student) -> None:
    """The admin helper picks whichever translation was entered first, which is
    fine for a list and wrong for a signed page — a school whose English name
    happened to be entered first would get it on the other language's page."""
    from app.models.content_version import ContentVersion

    course, _quiz = _course(db, teacher, "c-sheet-locale")
    cohort = Cohort(
        id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        status="active",
    )
    db.add(cohort)
    db.flush()
    # Russian entered first — the old resolver would have taken this one.
    db.add(
        ContentVersion(
            entity_type="cohort",
            entity_id=str(cohort.id),
            field="title",
            locale="ru",
            text="Поток 2026",
            origin="human",
        )
    )
    db.add(
        ContentVersion(
            entity_type="cohort",
            entity_id=str(cohort.id),
            field="title",
            locale="en",
            text="Class of 2026",
            origin="human",
        )
    )
    _enrol(db, course.id, STUDENT_ID, cohort_id=cohort.id)
    db.commit()

    sheet = admin_client.post(f"{SHEET_URL.format(course_id=course.id)}?cohort_id={cohort.id}").json()

    assert sheet["locale"] == "en"
    assert sheet["cohort_name"] == "Class of 2026"


def test_the_document_records_the_language_it_was_closed_in(admin_client, db: Session, teacher, student) -> None:
    """Every sheet closes in English by decision. The value is stored rather
    than assumed so that adding a language later costs nothing — without it,
    the day a second one appears, every sheet already in the cabinet is of
    unknown language and there is nothing to read it back from."""
    course, _quiz = _course(db, teacher, "c-sheet-records-locale")
    _enrol(db, course.id, STUDENT_ID)
    db.commit()

    sheet = admin_client.post(SHEET_URL.format(course_id=course.id)).json()

    assert sheet["locale"] == "en"
    assert sheet["course_title"] is not None, "the title is frozen too — courses get retitled"


def test_an_organization_heads_its_own_document_without_being_configured(client, db, teacher) -> None:
    """A ведомость carries the organization's name because it has one.

    Until 2026-08-27 the heading came only from ``org_settings``, which
    nothing filled in — so every ведомость printed unheaded until
    somebody ran an UPDATE against production. An organization always
    has a ``public_name``: it is NOT NULL, unique, and the thing a
    certificate prints. The settings columns remain as an override for
    an organization whose legal heading differs from the name it is
    known by.
    """
    from app.models.organization import Organization
    from app.services.grade_sheet_service import _letterhead

    course, _quiz = _course(db, teacher, "c-sheet-unconfigured")
    organization = db.query(Organization).filter(Organization.id == TEST_ORGANIZATION_ID).one()
    db.commit()

    letterhead = _letterhead(db, course, None)

    assert letterhead["school_name"] == organization.public_name


def test_the_letterhead_is_frozen_with_the_rest(admin_client, db: Session, teacher, student) -> None:
    """A school renames itself; a filed document does not.

    Read at print time, any of these rewrites the heading of every ведомость
    already signed — a 2024 page would start claiming this year's course length
    under next year's school name.
    """
    course, quiz = _course(db, teacher, "c-sheet-letterhead")
    course.academic_hours = 36
    # `get_org_settings` creates the single row on first read; the sheet path
    # is the only thing that touches it, so seed it here.
    from app.services.grading_scheme import get_org_settings

    settings = get_org_settings(db, TEST_ORGANIZATION_ID)
    settings.school_name_en = "Grace Bible School"
    settings.city = "Kyiv"
    _enrol(db, course.id, STUDENT_ID)
    _attempt(db, quiz, STUDENT_ID, 90)
    db.commit()

    signed = admin_client.post(SHEET_URL.format(course_id=course.id)).json()
    assert signed["school_name"] == "Grace Bible School"
    assert signed["school_city"] == "Kyiv"
    assert signed["academic_hours"] == 36
    assert signed["teacher_name"], "somebody taught it, and the page says who"

    settings.school_name_en = "Другое название"
    settings.city = "Другой город"
    course.academic_hours = 72
    db.commit()

    filed = admin_client.get(SHEET_URL.format(course_id=course.id)).json()

    assert filed["school_name"] == "Grace Bible School"
    assert filed["school_city"] == "Kyiv"
    assert filed["academic_hours"] == 36


def test_a_reading_only_pass_fail_course_is_not_failed_wholesale(admin_client, db: Session, teacher, student) -> None:
    """A course with nothing gradable has nothing to accept or refuse, whatever
    the scheme. The pass/fail branch used to sit above the completion check and
    stamped «незачёт» on every row of a reading-only course — its progress is 0
    because there are no gradable chapters to complete."""
    course = Course(id="c-sheet-reading", status="published", created_by=teacher.id, grading_scheme="pass_fail")
    db.add(course)
    module = Module(id="c-sheet-reading-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    db.add(
        Chapter(
            id="c-sheet-reading-ch",
            module_id=module.id,
            order_index=0,
            chapter_type="reading",
            title="Глава",
        )
    )
    _enrol(db, course.id, STUDENT_ID, progress=0)
    db.commit()

    row = admin_client.post(SHEET_URL.format(course_id=course.id)).json()["rows"][0]

    assert row["result_state"] == "completion_pass"


def test_a_retaking_students_sheet_reads_its_own_потока_progress(admin_client, db: Session, teacher, student) -> None:
    """Keyed by student with no cohort filter, a retaking student's two
    enrolments overwrote each other and *both* sheets read whichever came
    back last."""
    from app.models.assignment import Assignment, AssignmentSubmission

    course = Course(
        id="c-sheet-retake-progress",
        status="published",
        created_by=teacher.id,
        grading_scheme="pass_fail",
    )
    db.add(course)
    module = Module(id="c-sheet-retake-progress-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(
        id="c-sheet-retake-progress-ch",
        module_id=module.id,
        order_index=0,
        chapter_type="assignment",
        title="Работа",
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="graded",
            grade=80,
            graded_by=teacher.id,
        )
    )
    finished = Cohort(
        id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        status="completed",
    )
    db.add(finished)
    db.flush()
    db.add(
        Enrollment(
            id="enr-retake-done",
            user_id=STUDENT_ID,
            course_id=course.id,
            cohort_id=finished.id,
            progress=100,
        )
    )
    db.add(Enrollment(id="enr-retake-fresh", user_id=STUDENT_ID, course_id=course.id, progress=10))
    db.commit()

    row = admin_client.post(f"{SHEET_URL.format(course_id=course.id)}?cohort_id={finished.id}").json()["rows"][0]

    assert row["result_state"] == "pass", "the finished поток's page reads the finished enrolment"
