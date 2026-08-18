# Russian source text on purpose: these courses are written in one
# language and served in four, which is the situation being tested.
"""Translation happens without anyone remembering to ask for it.

The pipeline is event-driven, and events are the right shape for
latency and the wrong shape for certainty: they only ever notice what
somebody just touched. Two things never raise one.

**A language switched on after the content was written.** Every
existing course becomes incomplete in it at once, and nothing was
edited, so nothing fires. The documented remedy used to be a person
calling ``POST /courses/{id}/translate`` on each course in turn — a
hand-maintained list, which is fine for three courses and impossible
for a thousand.

**A pass that failed.** A provider outage, a deploy mid-flight, an
attempt cap reached. The course sits half-translated and the only thing
that would revive it is somebody happening to edit it again.

The sweep is the answer to both, and these tests are what hold it to
that: it finds the gap, it queues the work, it does not queue the same
course twice, it moves on rather than getting stuck on one course, and
it leaves drafts alone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.course import Course
from app.models.translation_job import TranslationJob, TranslationJobStatus
from app.models.user import User
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.translation.hash import compute_source_hash
from app.services.translation.reconciler import sweep_courses
from app.services.translation.service import reset_translation_provider_cache
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_TITLE = "Первое послание к Коринфянам"


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


def _course(db: Session, *, locales: tuple[str, ...], status: str = "published", checked=None) -> Course:
    """A course whose title exists in ``locales`` and nowhere else."""
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="t@example.com", role="teacher"))
        db.commit()
    course = Course(
        id=f"sweep-{uuid.uuid4().hex[:8]}",
        status=status,
        source_locale="ru",
        created_by=TEACHER_ID,
        translations_checked_at=checked,
    )
    db.add(course)
    db.commit()

    record_human_version(db, entity_type="course", entity_id=str(course.id), field="title", locale="ru", text=_TITLE)
    source_hash = compute_source_hash(_TITLE, locale="ru")
    for locale in locales:
        if locale == "ru":
            continue
        record_mt_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale=locale,
            text=f"[{locale}] First Corinthians",
            source_locale="ru",
            source_hash=source_hash,
        )
    db.commit()
    return course


def _queued_courses(db: Session) -> set[str]:
    return {
        job.course_id
        for job in db.query(TranslationJob).filter(TranslationJob.status == TranslationJobStatus.QUEUED).all()
    }


def test_a_language_nobody_edited_for_is_still_translated(db: Session):
    """The scenario this exists for. A course complete in three
    languages, a fourth switched on, nobody edits anything — and the
    work still gets queued."""
    course = _course(db, locales=("ru", "en", "de"))  # uk missing

    report = sweep_courses(db)

    assert report.queued == 1
    assert str(course.id) in _queued_courses(db)


def test_a_whole_course_is_left_alone(db: Session):
    """The sweep runs constantly. On a healthy catalogue it must cost a
    walk and a timestamp, not a queue entry and a Gemini bill."""
    _course(db, locales=("ru", "en", "de", "uk"))

    report = sweep_courses(db)

    assert report.examined == 1
    assert report.queued == 0
    assert report.complete == 1
    assert _queued_courses(db) == set()


def test_the_same_course_is_not_queued_twice(db: Session):
    """Two ticks before the worker gets to it must not mean two jobs and
    two bills."""
    _course(db, locales=("ru", "en"))

    sweep_courses(db)
    sweep_courses(db)

    assert len(db.query(TranslationJob).all()) == 1


def test_it_moves_on_instead_of_re_examining_the_same_course(db: Session):
    """Oldest-checked-first, and the timestamp is stamped whether or not
    a gap was found. Otherwise a course with a permanently unfixable
    field is re-examined forever while the rest of the catalogue waits
    behind it."""
    old = datetime.now(UTC) - timedelta(days=2)
    first = _course(db, locales=("ru", "en", "de", "uk"), checked=old)
    second = _course(db, locales=("ru", "en", "de", "uk"), checked=None)

    sweep_courses(db, limit=1)

    db.refresh(first)
    db.refresh(second)
    # NULL sorts first: the course nobody ever checked goes before the
    # one checked two days ago.
    assert second.translations_checked_at is not None
    # Compared without tzinfo: SQLite drops it on the way back out,
    # and what is being asserted is that the row was not touched.
    assert first.translations_checked_at.replace(tzinfo=UTC) == old

    sweep_courses(db, limit=1)
    db.refresh(first)
    assert first.translations_checked_at is not None, "the sweep should have moved on to the next course"


def test_drafts_are_left_to_their_author(db: Session):
    """A course being written all week would otherwise be re-translated
    all week, paying for wording that is still changing. Drafts
    translate on 'prepare for publication', not on a timer."""
    _course(db, locales=("ru",), status="draft")

    report = sweep_courses(db)

    assert report.examined == 0
    assert _queued_courses(db) == set()


def test_a_thousand_courses_are_examined_a_few_at_a_time(db: Session):
    """The check is a tree walk per course; doing every course every
    minute would make the sweep the heaviest thing on the database. It
    takes a slice and comes round again."""
    for _ in range(6):
        _course(db, locales=("ru", "en", "de", "uk"))

    report = sweep_courses(db, limit=3)

    assert report.examined == 3, "the sweep should take a slice, not the catalogue"
