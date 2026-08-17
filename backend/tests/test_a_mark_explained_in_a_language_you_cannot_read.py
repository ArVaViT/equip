"""A rubric is the sentence a student is given for their mark.

Everything else a reader sees had a translation path. This did not. The
criteria and the levels lived in their own columns and nowhere else, so
a German student opened their graded essay and read
«Аргумент опирается на текст» — the reason for their own grade, in a
language they never chose.

The rule that governs the rest of the platform is that a reader always
sees the language they picked and there is no spare one. A rubric bends
it in one specific way, deliberately: where a piece has no translation
yet, the author's text stands rather than a blank. A mark has already
been given; a student left with an empty criterion cannot see what they
were judged on at all, which is worse than seeing it in the wrong
language. It is the mirror of the same judgement the grading queue
makes for the teacher.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.rubric import AssignmentRubric, Rubric, RubricCriterion, RubricLevel
from app.services import rubric_service
from app.services.content_versions.write import record_human_version
from app.services.translation.course_tree import iter_course_entities
from app.services.translation.registry import REGISTRY

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

COURSE_ID = "rubric-lang-course"


def _course_with_graded_essay(db: Session):
    course = Course(id=COURSE_ID, status="published", created_by=TEACHER_ID, source_locale="ru")
    db.add(course)
    module = Module(id=f"{COURSE_ID}-m", course_id=COURSE_ID, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"{COURSE_ID}-a", module_id=module.id, order_index=0, chapter_type="assignment", title="Эссе")
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()

    rubric = Rubric(id=uuid.uuid4(), course_id=COURSE_ID, title="Эссе", created_by=TEACHER_ID)
    db.add(rubric)
    db.flush()
    criterion = RubricCriterion(
        id=uuid.uuid4(),
        rubric_id=rubric.id,
        order_index=0,
        title="Аргумент опирается на текст",
        description="Каждое утверждение подкреплено ссылкой",
    )
    db.add(criterion)
    db.flush()
    level = RubricLevel(
        id=uuid.uuid4(),
        criterion_id=criterion.id,
        order_index=0,
        label="Отлично",
        points=10,
        description="Ссылки точные и уместные",
    )
    db.add(level)
    db.add(AssignmentRubric(assignment_id=assignment.id, rubric_id=rubric.id))
    submission = AssignmentSubmission(
        id=uuid.uuid4(),
        assignment_id=assignment.id,
        student_id=STUDENT_ID,
        status="submitted",
        content="Работа",
    )
    db.add(submission)
    db.commit()
    return rubric, criterion, level, submission


class TestTheRubricIsTranslatableAtAll:
    def test_every_piece_of_it_is_registered(self):
        # Without a registry row nothing walks it, nothing translates it,
        # and the gap is invisible to every completeness check.
        for entity_type in ("rubric", "rubric_criterion", "rubric_level"):
            assert entity_type in REGISTRY, f"{entity_type} has no translation path"

    def test_the_course_walk_reaches_it(self, db: Session, teacher, student):
        rubric, criterion, level, _submission = _course_with_graded_essay(db)
        course = db.query(Course).filter(Course.id == COURSE_ID).one()

        walked = {(kind, str(entity.id)) for kind, entity in iter_course_entities(db, course)}

        # The backfill is this walk. A rubric outside it is a rubric that
        # is never translated, however well the rest of the course is.
        assert ("rubric", str(rubric.id)) in walked
        assert ("rubric_criterion", str(criterion.id)) in walked
        assert ("rubric_level", str(level.id)) in walked


class TestWhatTheStudentReads:
    def test_the_criterion_arrives_in_their_own_language(self, db: Session, teacher, student):
        rubric, criterion, level, _submission = _course_with_graded_essay(db)
        record_human_version(
            db,
            entity_type="rubric_criterion",
            entity_id=str(criterion.id),
            field="title",
            locale="de",
            text="Das Argument stützt sich auf den Text",
        )
        record_human_version(
            db,
            entity_type="rubric_level",
            entity_id=str(level.id),
            field="title",
            locale="de",
            text="Ausgezeichnet",
        )
        db.commit()

        payload = rubric_service.rubric_payload(db, rubric, display_locale="de", source_locale="ru")

        assert payload["criteria"][0]["title"] == "Das Argument stützt sich auf den Text"
        assert payload["criteria"][0]["levels"][0]["label"] == "Ausgezeichnet"

    def test_an_untranslated_piece_still_says_what_was_judged(self, db: Session, teacher, student):
        # Not a blank. The mark has been given; hiding the criterion
        # leaves the student unable to see what it was given for.
        rubric, _criterion, _level, _submission = _course_with_graded_essay(db)

        payload = rubric_service.rubric_payload(db, rubric, display_locale="de", source_locale="ru")

        assert payload["criteria"][0]["title"] == "Аргумент опирается на текст"

    def test_the_author_still_sees_their_own_words(self, db: Session, teacher, student):
        # No display locale asked for: the teacher writing the rubric.
        rubric, _criterion, _level, _submission = _course_with_graded_essay(db)

        payload = rubric_service.rubric_payload(db, rubric)

        assert payload["criteria"][0]["title"] == "Аргумент опирается на текст"


class TestTheRoute:
    def test_it_answers_in_the_language_asked_for(self, student_client: TestClient, db: Session, teacher, student):
        _rubric, criterion, _level, submission = _course_with_graded_essay(db)
        record_human_version(
            db,
            entity_type="rubric_criterion",
            entity_id=str(criterion.id),
            field="title",
            locale="de",
            text="Das Argument stützt sich auf den Text",
        )
        db.commit()

        response = student_client.get(
            f"/api/v1/rubrics/submission/{submission.id}",
            headers={"Accept-Language": "de"},
        )

        assert response.status_code == 200
        assert response.json()["rubric"]["criteria"][0]["title"] == "Das Argument stützt sich auf den Text"

    def test_the_answer_says_it_varies_by_language(self, student_client: TestClient, db: Session, teacher, student):
        _rubric, _criterion, _level, submission = _course_with_graded_essay(db)

        response = student_client.get(
            f"/api/v1/rubrics/submission/{submission.id}",
            headers={"Accept-Language": "de"},
        )

        assert response.headers.get("Vary") == "Accept-Language"
