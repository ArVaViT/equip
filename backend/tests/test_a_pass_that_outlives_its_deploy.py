"""A translation pass is longer than the code it started in.

A worker tick runs for up to 180 seconds and the cron fires every
minute, so several ticks are always in flight together. A deploy lands
in the middle of that: some passes are running the pipeline that was
just replaced, and they will keep running it until they finish.

``TRANSLATOR_VERSION`` is the number that says which pipeline made a
row, and every phase of a pass consults it — deciding what is already
done, deciding which stored wording may be reused, seeding the term
memory, stamping each row that gets written. Read at each point of use,
it is a moving target, and the rows of one plan stop agreeing about
which pipeline made them. Production holds a pair written in the same
transaction — same ``created_at`` to the microsecond — reading 7 and 8.

What that costs is not bookkeeping. Everything that compares two rows
by generation is then comparing rows that were never in competition,
and the answer-option collision check is the one that parks a row
permanently for it: nine rows in production are held back as
``option_collision`` against siblings that no longer say anything of
the kind.

So a run decides its generation once and carries it, and the collision
check stops asking about generations at all — it asks whether the pass
it belongs to is about to rewrite the sibling it is looking at.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.user import User
from app.services.content_versions import record_human_version, record_mt_version
from app.services.translation.executor import TranslationTask, execute_plan
from app.services.translation.hash import compute_source_hash
from app.services.translation.protocol import TranslationResult
from app.services.translation.service import reset_translation_provider_cache
from app.services.translation.stores import LIVE_STORE
from app.services.translation.version import TRANSLATOR_VERSION

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-00000000de91")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


class _Scripted:
    """Answers from a table, and can let a deploy land between calls."""

    name = "scripted"

    def __init__(self, answers: dict[str, str], *, on_call=None) -> None:
        self._answers = answers
        self._on_call = on_call
        self.calls: list[str] = []

    def translate(self, request):
        self.calls.append(request.text)
        if self._on_call is not None:
            self._on_call(len(self.calls))
        return TranslationResult(text=self._answers[request.text], model="fake")


def _task(entity_id: str, *, text: str, source_hash: str | None = None) -> TranslationTask:
    return TranslationTask(
        entity_type="quiz_option",
        entity_id=entity_id,
        field="option_text",
        source_locale="ru",
        target_locale="en",
        text=text,
        content_kind="quiz_option",
        source_hash=source_hash or compute_source_hash(text, locale="ru"),
    )


@pytest.fixture
def two_options(db: Session) -> tuple[QuizOption, QuizOption]:
    """One question, two options, both with their Russian written."""
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="deploy@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.flush()
    module = Module(id=f"mod-{uuid.uuid4().hex[:8]}", course_id=course.id, title="Модуль", order_index=0)
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"ch-{uuid.uuid4().hex[:8]}", module_id=module.id, title="Глава", order_index=0)
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, order_index=0, question_type="multiple_choice")
    db.add(question)
    db.flush()
    right = QuizOption(id=uuid.uuid4(), question_id=question.id, order_index=0, is_correct=True)
    wrong = QuizOption(id=uuid.uuid4(), question_id=question.id, order_index=1, is_correct=False)
    db.add_all([right, wrong])
    db.commit()
    for option, text in ((right, "Мальта"), (wrong, "Крит")):
        record_human_version(
            db,
            entity_type="quiz_option",
            entity_id=str(option.id),
            field="option_text",
            locale="ru",
            text=text,
        )
    db.commit()
    return right, wrong


def _row(db: Session, option: QuizOption) -> ContentVersion:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_id == str(option.id),
            ContentVersion.locale == "en",
            ContentVersion.superseded_by.is_(None),
        )
        .one()
    )


class TestOneRunIsOnePipeline:
    def test_a_deploy_between_two_batches_does_not_split_the_plan(self, db: Session, monkeypatch) -> None:
        """The production shape: one plan, two generations.

        The pass starts under one number and a deploy raises it while
        the pass is still going. Read at each write, the constant stamps
        the first half of the plan with the pipeline that made it and
        the second half with a pipeline that had nothing to do with it —
        and every later comparison between those rows is meaningless.

        The number belongs to the run. Rows written after the deploy are
        below the new constant, so the reconciler sweep finds them and
        they are made again properly. Half a batch stamped each way is
        the one outcome nothing can repair, because both halves look
        finished.
        """
        old = TRANSLATOR_VERSION
        monkeypatch.setattr("app.services.translation.executor.TRANSLATOR_VERSION", old)
        monkeypatch.setattr("app.services.content_versions.write.TRANSLATOR_VERSION", old)

        def deploy_after_the_first_row(call: int) -> None:
            # The second batch goes out under the new code; the first
            # option has already been asked for, answered and written.
            if call == 2:
                monkeypatch.setattr("app.services.translation.executor.TRANSLATOR_VERSION", old + 1)
                monkeypatch.setattr("app.services.content_versions.write.TRANSLATOR_VERSION", old + 1)

        provider = _Scripted(
            {"Мальта": "Malta", "Крит": "Crete"},
            on_call=deploy_after_the_first_row,
        )
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        tasks = [_task(first, text="Мальта"), _task(second, text="Крит")]

        execute_plan(db, tasks, provider=provider, store=LIVE_STORE, max_workers=1)
        db.commit()

        stamped = {
            row.translator_version
            for row in db.query(ContentVersion).filter(ContentVersion.entity_id.in_([first, second]))
        }
        assert stamped == {old}, f"one plan, one pipeline — got {sorted(stamped)}"


class TestARebuildDoesNotParkItsOwnCorrections:
    def test_the_sibling_this_pass_is_about_to_rewrite_parks_nothing(self, db: Session, two_options) -> None:
        """The nine rows, in the shape they were made.

        An earlier pass answered both options of this question "Malta" —
        the model, told what question it was answering, helpfully
        repaired the wrong one. The author has since edited the Russian
        of the wrong option, so this pass is holding a task for it and
        will replace that "Malta" within the minute.

        Before it gets there it translates the *correct* option, whose
        answer is "Malta" and is meant to be. The old check compared it
        against the sibling's soon-to-be-gone text and parked it — a
        correct translation, held back for matching a wrong one, and
        held back for good: a parked row moves only when its source
        changes, and the source is fine.

        Nothing about generations separates those two rows. The sibling
        was written by the pipeline in force, which is the whole reason
        the version guard did not catch this. What separates them is
        that one of them is this pass's own unfinished work.
        """
        right, wrong = two_options
        # What the previous pass left: both options reading "Malta".
        for option in (right, wrong):
            record_mt_version(
                db,
                entity_type="quiz_option",
                entity_id=str(option.id),
                field="option_text",
                locale="en",
                text="Malta",
                source_locale="ru",
                source_hash=compute_source_hash("Крит", locale="ru"),
                translator_version=TRANSLATOR_VERSION,
            )
        db.commit()

        # This pass: the correct option first, the edited wrong one
        # second. Both are due — the right one because its source hash
        # never matched, the wrong one because the author rewrote it.
        provider = _Scripted({"Мальта": "Malta", "Крит, остров": "Crete, the island"})
        tasks = [
            _task(str(right.id), text="Мальта"),
            _task(str(wrong.id), text="Крит, остров"),
        ]

        result = execute_plan(db, tasks, provider=provider, store=LIVE_STORE, max_workers=1)
        db.commit()

        correct = _row(db, right)
        assert correct.text == "Malta"
        assert correct.status == "ok", f"parked for {correct.review_reason!r}"
        assert result.needs_review == 0
        assert _row(db, wrong).text == "Crete, the island"

    def test_a_duplicate_this_pass_made_itself_is_still_caught(self, db: Session, two_options) -> None:
        """The check still does the thing it was written for.

        Both options come back reading "Malta" from this very pass. The
        first one written is the text on the page by the time the second
        is checked, so the second is parked — which is the right one to
        park, because it is the one that turned a question into a coin
        toss.
        """
        right, wrong = two_options
        provider = _Scripted({"Мальта": "Malta", "Крит": "Malta"})
        tasks = [
            _task(str(right.id), text="Мальта"),
            _task(str(wrong.id), text="Крит"),
        ]

        result = execute_plan(db, tasks, provider=provider, store=LIVE_STORE, max_workers=1)
        db.commit()

        assert result.needs_review == 1
        assert _row(db, right).status == "ok"
        parked = _row(db, wrong)
        assert parked.status == "needs_review"
        assert "option_collision" in (parked.review_reason or "")
