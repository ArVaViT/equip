"""A gap the pass cannot reach is not work, and must not be queued as work.

Measured in production on 2026-08-20. A published course with
``source_locale = 'ru'`` had exactly one active human row for its
``title``, and that row was English:

    field  locale  origin  status  text
    title  en      human   ok      "Language walkthrough 2026-08-19 1931 (test)"

``course_translation_completeness`` read that row — ``_authored_texts``
deliberately answers at ANY locale — decided the title's source language
was English, and required de, ru and uk. All three came back
``reason='missing'``, which is actionable, so ``sweep_courses`` queued
the course.

The pass that ran never touched the field. ``plan_course_tasks`` walks a
course fetched through ``get_course``, which hydrates it: no ``ru`` row
exists, so ``populate_spine_texts`` sets ``course.title = ""`` — "nothing
in the language you asked for". ``entity_field_specs`` then read ``""``
as "the author wrote nothing" and dropped the field. Zero tasks.

645 jobs, one every two minutes for a day (enqueued :25:01, :27:01,
:29:01 … — an idle tick sweeps and queues, the next tick claims and
finishes in two seconds with nothing done, the tick after that sweeps
again), every one of them ending ``done``.

The damage was not the jobs. ``sweep_courses`` and the idle Daily
Challenge pool sweep both run only when ``claim_next_job`` returns None,
and the sweep returned early the moment it queued anything — so the pool
sweep never got a tick. 2,988 Daily Challenge rows sat at pipeline
generation 2 while the course tree reached 10.

Hydration bites twice in the same course, in opposite directions. Fix
only the blank and the next pass resolves ``title`` at ``source_locale``
to the machine's own Russian and hands it back as the source — the pass
would re-translate its own output under a hash the gate does not expect,
which is the same loop one generation further from the author. So the
author's text is read from the author's rows, always, and the model
attribute is the fallback rather than the other way round.

Two things are tested here, because the fix is two things:

* ``entity_field_specs`` resolves the source from cv human rows for
  every field, so its answer is a function of the database alone and
  cannot depend on which caller hydrated what. That closes this hole:
  the English title is planned, translated into the other three, and the
  publication gate holds the course in ``publishing`` until they land.
* ``sweep_courses`` refuses to queue a course when the plan it is about
  to run produces no task for any of its actionable gaps — a backstop
  for the next disagreement, which will have a shape none of us guessed.

And the thing that must not break: a course with a real, fillable gap
still gets queued, every time. That failure would be silent, which is
worse than this one.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion
from app.models.course import Course, CourseStatus, Module
from app.models.user import User
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.course_service import get_course
from app.services.translation.completeness import course_translation_completeness, promote_if_complete
from app.services.translation.course_pipeline import plan_course_tasks
from app.services.translation.hash import compute_source_hash
from app.services.translation.reconciler import sweep_courses
from app.services.translation.registry import entity_field_specs
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d7")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


def _teacher(db: Session) -> None:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="plan-reach@example.com", full_name="T", role="teacher"))
        db.commit()


def _translated_course(db: Session) -> Course:
    """A settled Russian course: every field human in ``ru``, machine
    everywhere else. The sweep should find nothing to do with it."""
    _teacher(db)
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.flush()
    module = Module(
        id=f"mod-{uuid.uuid4().hex[:8]}",
        course_id=course.id,
        title="Первый модуль",
        order_index=0,
    )
    db.add(module)
    db.commit()

    for entity_type, entity_id, field, text in (
        ("course", str(course.id), "title", "Послание к Римлянам"),
        ("course", str(course.id), "description", "Письмо апостола Павла: разбор по главам"),
        ("module", str(module.id), "title", "Первый модуль"),
        ("module", str(module.id), "description", "Здесь начинается первая часть"),
    ):
        record_human_version(db, entity_type=entity_type, entity_id=entity_id, field=field, locale="ru", text=text)
        source_hash = compute_source_hash(text, locale="ru")
        for locale in ("en", "de", "uk"):
            record_mt_version(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                locale=locale,
                text=f"{text} [{locale}]",
                source_locale="ru",
                source_hash=source_hash,
            )
    db.commit()
    return course


def _course_titled_only_in_english(db: Session) -> Course:
    """The production shape: a Russian course whose only human ``title``
    row is English, and no row at ``ru`` at all."""
    course = _translated_course(db)
    db.query(ContentVersion).filter(
        ContentVersion.entity_type == "course",
        ContentVersion.entity_id == str(course.id),
        ContentVersion.field == "title",
    ).delete()
    db.commit()
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="en",
        text="Language walkthrough 2026-08-19 1931 (test)",
    )
    db.commit()
    db.expire_all()
    return course


class TestTheCheckAndThePlanSeeTheSameField:
    def test_a_hydrated_blank_title_no_longer_hides_the_authors_row(self, db: Session) -> None:
        # ``get_course`` hydrates, and with no ``ru`` row the hydration
        # writes ``""``. That must not read as "the author wrote nothing".
        course = _course_titled_only_in_english(db)
        hydrated = get_course(db, str(course.id))
        assert hydrated is not None
        assert hydrated.title == "", "the hydration artefact this bug rode in on"

        specs = {spec.field: spec for spec in entity_field_specs(db, "course", hydrated, "ru")}
        assert "title" in specs
        assert specs["title"].text == "Language walkthrough 2026-08-19 1931 (test)"
        assert specs["title"].source_locale == "en"

    def test_the_plan_now_contains_the_three_languages_the_check_demands(self, db: Session) -> None:
        course = _course_titled_only_in_english(db)
        gaps = {
            (gap.field, gap.locale)
            for gap in course_translation_completeness(db, course).gaps
            if gap.entity_type == "course"
        }
        assert gaps == {("title", "de"), ("title", "ru"), ("title", "uk")}

        planned = {
            (task.field, task.target_locale)
            for task in plan_course_tasks(db, get_course(db, str(course.id)))
            if task.entity_type == "course"
        }
        assert gaps <= planned, "the pass must produce a task for every gap the gate demands"

    def test_the_pipeline_is_never_handed_back_its_own_output(self, db: Session) -> None:
        # The same hydration, one step later and in the opposite
        # direction. Once a Russian translation of the English title
        # exists, ``populate_spine_texts`` resolves ``course.title`` at
        # the course's ``source_locale`` — and finds the machine's own
        # Russian. Read as the source, that re-translates the pipeline's
        # output under a hash the gate does not expect: the same loop
        # again, one generation further from the author every pass.
        course = _course_titled_only_in_english(db)
        english = "Language walkthrough 2026-08-19 1931 (test)"
        for locale in ("de", "ru", "uk"):
            record_mt_version(
                db,
                entity_type="course",
                entity_id=str(course.id),
                field="title",
                locale=locale,
                text=f"{english} [{locale}]",
                source_locale="en",
                source_hash=compute_source_hash(english, locale="en"),
            )
        db.commit()

        hydrated = get_course(db, str(course.id))
        assert hydrated is not None
        assert hydrated.title == f"{english} [ru]", "the machine's own Russian, resolved for display"

        specs = {spec.field: spec for spec in entity_field_specs(db, "course", hydrated, "ru")}
        assert specs["title"].text == english
        assert specs["title"].source_locale == "en"

    def test_a_field_with_no_text_anywhere_is_required_of_nobody(self, db: Session) -> None:
        # The other half of "you cannot translate nothing": a course
        # nobody has written a description for is not three gaps, it is
        # no gap. Mid-authoring must stay free.
        course = _translated_course(db)
        db.query(ContentVersion).filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id == str(course.id),
            ContentVersion.field == "description",
        ).delete()
        db.commit()
        db.expire_all()

        completeness = course_translation_completeness(db, course)
        assert [gap for gap in completeness.gaps if gap.field == "description"] == []
        assert completeness.is_complete


class TestThePublicationGateCatchesItToo:
    """Should a published course with no title in its own source language
    be publishable? It already was not — the gate is
    ``course_translation_completeness``, and it demands the other three
    languages of whatever the author wrote. What let this course through
    was that the gate ran on a *hydrated* course and so saw no title at
    all. With blank read as absent, the same gate holds it back, and no
    new rule is needed."""

    def test_a_course_titled_only_in_english_is_not_promoted(self, db: Session) -> None:
        course = _course_titled_only_in_english(db)
        course.status = CourseStatus.PUBLISHING
        db.commit()

        hydrated = get_course(db, str(course.id))
        assert hydrated is not None
        assert promote_if_complete(db, hydrated) is False
        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHING

    def test_and_is_promoted_once_the_three_languages_arrive(self, db: Session) -> None:
        course = _course_titled_only_in_english(db)
        course.status = CourseStatus.PUBLISHING
        db.commit()

        english = "Language walkthrough 2026-08-19 1931 (test)"
        for locale in ("de", "ru", "uk"):
            record_mt_version(
                db,
                entity_type="course",
                entity_id=str(course.id),
                field="title",
                locale=locale,
                text=f"{english} [{locale}]",
                source_locale="en",
                source_hash=compute_source_hash(english, locale="en"),
            )
        db.commit()

        hydrated = get_course(db, str(course.id))
        assert hydrated is not None
        assert promote_if_complete(db, hydrated) is True
        db.refresh(course)
        assert course.status == CourseStatus.PUBLISHED


class TestTheSweepWillNotQueueAPassWithNothingToDo:
    def test_a_course_whose_gaps_the_plan_never_reaches_is_not_queued(self, db: Session) -> None:
        # The general guard, exercised on a gap the specific fix does not
        # close: the check demands a language the plan has no task for.
        course = _translated_course(db)
        db.query(ContentVersion).filter(
            ContentVersion.entity_id == str(course.id),
            ContentVersion.locale == "de",
            ContentVersion.origin == "mt",
        ).delete()
        db.commit()

        real_plan = plan_course_tasks

        def plan_without_german(db_, course_):
            return [task for task in real_plan(db_, course_) if task.target_locale != "de"]

        with (
            patch("app.services.translation.course_pipeline.plan_course_tasks", plan_without_german),
            patch("app.services.translation.reconciler.enqueue_course_translation") as enqueue,
        ):
            report = sweep_courses(db, limit=5)

        enqueue.assert_not_called()
        assert report.queued == 0
        assert report.stalled == 1

    def test_and_it_stops_looping_rather_than_queueing_forever(self, db: Session) -> None:
        course = _translated_course(db)
        db.query(ContentVersion).filter(
            ContentVersion.entity_id == str(course.id),
            ContentVersion.locale == "de",
            ContentVersion.origin == "mt",
        ).delete()
        db.commit()

        real_plan = plan_course_tasks

        def plan_without_german(db_, course_):
            return [task for task in real_plan(db_, course_) if task.target_locale != "de"]

        with patch("app.services.translation.course_pipeline.plan_course_tasks", plan_without_german):
            queued = [sweep_courses(db, limit=5).queued for _ in range(4)]
        assert queued == [0, 0, 0, 0], "sixty jobs in two hours is what this number was"

    def test_a_stalled_course_is_still_timestamped(self, db: Session) -> None:
        # Otherwise it sorts first forever and starves the others.
        course = _translated_course(db)
        db.query(ContentVersion).filter(
            ContentVersion.entity_id == str(course.id),
            ContentVersion.locale == "de",
            ContentVersion.origin == "mt",
        ).delete()
        db.commit()

        real_plan = plan_course_tasks

        def plan_without_german(db_, course_):
            return [task for task in real_plan(db_, course_) if task.target_locale != "de"]

        with patch("app.services.translation.course_pipeline.plan_course_tasks", plan_without_german):
            sweep_courses(db, limit=5)
        db.refresh(course)
        assert course.translations_checked_at is not None


class TestTheGuardDoesNotSwallowRealWork:
    """The opposite bug is worse: a course that silently stops being
    translated shows nothing at all, where this one at least showed a
    queue that never emptied."""

    def test_a_genuine_missing_language_is_still_queued(self, db: Session) -> None:
        course = _translated_course(db)
        db.query(ContentVersion).filter(
            ContentVersion.entity_id == str(course.id),
            ContentVersion.locale == "de",
            ContentVersion.origin == "mt",
        ).delete()
        db.commit()

        report = sweep_courses(db, limit=5)
        assert report.queued == 1
        assert report.stalled == 0

    def test_the_english_only_title_is_now_work_the_sweep_queues(self, db: Session) -> None:
        # The production course itself: after the fix its gap is real and
        # fillable, so it is queued — once, for a job that does something.
        _course_titled_only_in_english(db)
        report = sweep_courses(db, limit=5)
        assert report.queued == 1
        assert report.stalled == 0

    def test_a_course_whose_gaps_shrink_keeps_being_worked_on(self, db: Session) -> None:
        # The guard must be a statement about the plan, never a memory of
        # having queued before. Two languages missing, one filled in, and
        # the course keeps its place in the queue.
        course = _translated_course(db)
        for locale in ("de", "uk"):
            db.query(ContentVersion).filter(
                ContentVersion.entity_id == str(course.id),
                ContentVersion.locale == locale,
                ContentVersion.origin == "mt",
            ).delete()
        db.commit()
        assert sweep_courses(db, limit=5).queued == 1

        for entity_type, entity_id, field, text in (
            ("course", str(course.id), "title", "Послание к Римлянам"),
            ("course", str(course.id), "description", "Письмо апостола Павла: разбор по главам"),
        ):
            record_mt_version(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                locale="de",
                text=f"{text} [de]",
                source_locale="ru",
                source_hash=compute_source_hash(text, locale="ru"),
            )
        db.commit()

        report = sweep_courses(db, limit=5)
        assert report.queued == 1, "uk is still missing and the plan can still close it"
        assert report.stalled == 0

    def test_a_settled_course_costs_nothing_and_queues_nothing(self, db: Session) -> None:
        _translated_course(db)
        report = sweep_courses(db, limit=5)
        assert (report.queued, report.stalled) == (0, 0)
        assert report.complete == 1
