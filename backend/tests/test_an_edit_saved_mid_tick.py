"""An edit made while the worker is busy must not fall through the floor.

The worker reads held edits once, at the start of its tick, and marks
the job done at the end. Enqueue used to treat a job already
``processing`` as standing in for a new one — so an edit saved in
between was staged, found a "pending" job, enqueued nothing, and was
left with no job at all.

Nothing else would find it either. The reconciler decides what to do by
reading ``content_versions``, and the edit is sitting in
``staged_content_versions`` with the old, complete text still live. So
the correction stayed invisible to every student until the teacher
happened to save that course again.

The window is one whole tick — up to the worker's full budget — and a
large course is processing for most of every tick.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.course import Course, CourseStatus
from app.models.translation_job import TranslationJob, TranslationJobStatus
from app.models.user import User
from app.services.translation.queue import enqueue_course_translation

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

COURSE_ID = "course-mid-tick"
TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e9")


@pytest.fixture(autouse=True)
def _a_course_to_hang_jobs_on(db: Session) -> None:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="midtick@example.com", full_name="T", role="teacher"))
        db.commit()
    if db.get(Course, COURSE_ID) is None:
        db.add(
            Course(
                id=COURSE_ID,
                status=CourseStatus.PUBLISHED,
                source_locale="ru",
                created_by=TEACHER_ID,
            )
        )
        db.commit()


def _jobs(db: Session) -> list[TranslationJob]:
    return db.query(TranslationJob).filter(TranslationJob.course_id == COURSE_ID).all()


class TestAJobAlreadyRunningDoesNotStandIn:
    def test_an_edit_during_processing_gets_its_own_job(self, db: Session) -> None:
        db.add(
            TranslationJob(
                id=uuid.uuid4(),
                course_id=COURSE_ID,
                status=TranslationJobStatus.PROCESSING,
            )
        )
        db.commit()

        enqueue_course_translation(db, COURSE_ID)

        statuses = sorted(job.status for job in _jobs(db))
        assert statuses == [TranslationJobStatus.PROCESSING, TranslationJobStatus.QUEUED]

    def test_a_queued_job_still_stands_in(self, db: Session) -> None:
        # The idempotence that matters is unchanged: a job that has not
        # started yet will pick up whatever is staged when it runs, so a
        # second row would be pure duplication.
        first = enqueue_course_translation(db, COURSE_ID)
        second = enqueue_course_translation(db, COURSE_ID)
        assert first.id == second.id
        assert len(_jobs(db)) == 1

    def test_a_finished_job_does_not_stand_in_either(self, db: Session) -> None:
        db.add(
            TranslationJob(
                id=uuid.uuid4(),
                course_id=COURSE_ID,
                status=TranslationJobStatus.DONE,
            )
        )
        db.commit()

        enqueue_course_translation(db, COURSE_ID)

        assert any(job.status == TranslationJobStatus.QUEUED for job in _jobs(db))


class TestTheSameWordsAskedTwoDifferentWays:
    """Identical text is asked about once — unless the question differs.

    Deduplication exists because 27% of the corpus is duplicate source
    text: answer options repeat "True", "Yes", "Neither of these" across
    quizzes, and asking the provider once for all of them is most of the
    saving in a pass.

    But the batch was keyed on the text alone, and the text is not the
    whole question. A sentence sent as `html` is told to preserve markup;
    the same sentence sent as `quiz_option` is told not to grow into a
    paragraph. The first task's kind answered for both, and the second
    row was written having never been checked under its own rules —
    validation runs once, on the representative.
    """

    def test_two_kinds_are_two_questions(self, db: Session) -> None:
        from app.services.translation.executor import TranslationTask, execute_plan
        from app.services.translation.protocol import TranslationRequest, TranslationResult
        from app.services.translation.stores import LIVE_STORE

        class _Recorder:
            def __init__(self) -> None:
                self.asked: list[str] = []

            def translate(self, request: TranslationRequest) -> TranslationResult:
                self.asked.append(request.content_kind)
                return TranslationResult(text="ANSWER", model="fake")

        shared = "Trust in the Lord"
        tasks = [
            TranslationTask(
                entity_type="chapter_block",
                entity_id=str(uuid.uuid4()),
                field="content",
                source_locale="en",
                target_locale="ru",
                text=shared,
                content_kind="html",
                source_hash="same-hash",
            ),
            TranslationTask(
                entity_type="quiz_option",
                entity_id=str(uuid.uuid4()),
                field="option_text",
                source_locale="en",
                target_locale="ru",
                text=shared,
                content_kind="quiz_option",
                source_hash="same-hash",
            ),
        ]
        provider = _Recorder()

        class _Store:
            name = "test"

            def active_row(self, *args, **kwargs):
                return None

            def active_rows(self, db, keys):
                return {}

            def record_success(self, *args, **kwargs) -> None:
                return None

            def record_failure(self, *args, **kwargs) -> None:
                return None

        execute_plan(db, tasks, provider=provider, store=_Store(), max_workers=2)  # type: ignore[arg-type]
        assert sorted(provider.asked) == ["html", "quiz_option"]
        assert LIVE_STORE is not None

    def test_the_same_kind_is_still_asked_once(self, db: Session) -> None:
        # The saving this exists for must survive the fix.
        from app.services.translation.executor import TranslationTask, execute_plan
        from app.services.translation.protocol import TranslationRequest, TranslationResult

        class _Recorder:
            def __init__(self) -> None:
                self.calls = 0

            def translate(self, request: TranslationRequest) -> TranslationResult:
                self.calls += 1
                return TranslationResult(text="ANSWER", model="fake")

        tasks = [
            TranslationTask(
                entity_type="quiz_option",
                entity_id=str(uuid.uuid4()),
                field="option_text",
                source_locale="en",
                target_locale="ru",
                text="True",
                content_kind="quiz_option",
                source_hash="twin-hash",
            )
            for _ in range(4)
        ]
        provider = _Recorder()

        class _Store:
            name = "test"

            def active_row(self, *args, **kwargs):
                return None

            def active_rows(self, db, keys):
                return {}

            def record_success(self, *args, **kwargs) -> None:
                return None

            def record_failure(self, *args, **kwargs) -> None:
                return None

        execute_plan(db, tasks, provider=provider, store=_Store(), max_workers=4)  # type: ignore[arg-type]
        assert provider.calls == 1
