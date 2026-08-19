"""A field the platform cannot see is a field it cannot promise anything about.

Eight entity types keep their text only in ``content_versions`` —
chapter blocks, quizzes, questions, options, assignments, announcements,
events, cohorts. Their source text was read at the course's declared
locale with the reader-facing resolver, which answers ``None`` when
nothing exists in the locale asked for. That is right for a reader and
wrong here: ``dual_write`` files a human row under the language the text
is actually in, not the language the course declares.

So a teacher who pastes an English paragraph into a Russian course had
it filed under ``en``, asked for at ``ru``, and dropped. The field then
existed for nobody:

* ``plan_course_tasks`` produced no task for it — never translated;
* ``course_translation_completeness`` required no locale for it — so the
  publication gate, written precisely to keep a half-translated course
  out of the catalogue, counted the hole as nothing at all.

Both halves of the safety net were blind to the same field, which is
what makes this the worst shape a defect can take here. The platform's
premise is authors in four languages; this is that premise failing
silently.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.user import User
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.course_pipeline import plan_course_tasks
from app.services.translation.hash import compute_source_hash
from app.services.translation.registry import entity_field_specs
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d4")

ENGLISH = "<p>Paul came to Corinth and stayed there for eighteen months, teaching the word of God.</p>"
RUSSIAN = "<p>Павел пришёл в Коринф и оставался там полтора года, уча слову Божию.</p>"


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


def _russian_course_with_a_block(db: Session, *, text: str, locale: str) -> tuple[Course, ChapterBlock]:
    """A course declared Russian, carrying one block authored in ``locale``."""
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="mixed@example.com", full_name="T", role="teacher"))
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
    block = ChapterBlock(id=uuid.uuid4(), chapter_id=chapter.id, block_type="text", order_index=0)
    db.add(block)
    db.commit()

    record_human_version(
        db,
        entity_type="chapter_block",
        entity_id=str(block.id),
        field="content",
        locale=locale,
        text=text,
    )
    db.commit()
    return course, block


class TestTheFieldIsSeen:
    def test_an_english_paragraph_in_a_russian_course_has_a_source(self, db: Session) -> None:
        _course, block = _russian_course_with_a_block(db, text=ENGLISH, locale="en")
        specs = entity_field_specs(db, "chapter_block", block, "ru")
        assert [spec.field for spec in specs] == ["content"]
        assert specs[0].source_locale == "en", "the field's language is where its row is filed"

    def test_the_control_still_behaves(self, db: Session) -> None:
        # The same block authored in the declared language, so a failure
        # above cannot be blamed on the fixture.
        _course, block = _russian_course_with_a_block(db, text=RUSSIAN, locale="ru")
        specs = entity_field_specs(db, "chapter_block", block, "ru")
        assert [spec.field for spec in specs] == ["content"]
        assert specs[0].source_locale == "ru"


class TestBothHalvesOfTheNetSeeIt:
    def test_it_is_planned_for_every_other_language(self, db: Session) -> None:
        course, block = _russian_course_with_a_block(db, text=ENGLISH, locale="en")
        planned = {task.target_locale for task in plan_course_tasks(db, course) if task.entity_id == str(block.id)}
        assert planned == {"ru", "de", "uk"}, "an English source needs the other three"

    def test_the_publication_gate_requires_it(self, db: Session) -> None:
        course, block = _russian_course_with_a_block(db, text=ENGLISH, locale="en")
        gaps = {
            gap.locale for gap in course_translation_completeness(db, course).gaps if gap.entity_id == str(block.id)
        }
        assert gaps == {"ru", "de", "uk"}

    def test_and_stops_requiring_it_once_it_is_translated(self, db: Session) -> None:
        course, block = _russian_course_with_a_block(db, text=ENGLISH, locale="en")
        source_hash = compute_source_hash(ENGLISH, locale="en")
        for locale in ("ru", "de", "uk"):
            record_mt_version(
                db,
                entity_type="chapter_block",
                entity_id=str(block.id),
                field="content",
                locale=locale,
                text=f"<p>[{locale}]</p>",
                source_locale="en",
                source_hash=source_hash,
            )
        db.commit()
        remaining = [gap for gap in course_translation_completeness(db, course).gaps if gap.entity_id == str(block.id)]
        assert remaining == []


class TestTheSourceIsAlwaysAPersonsText:
    def test_a_machine_row_is_never_treated_as_the_source(self, db: Session) -> None:
        # Otherwise the pipeline translates its own output and the course
        # drifts one language further from its author on every pass.
        course, block = _russian_course_with_a_block(db, text=ENGLISH, locale="en")
        record_mt_version(
            db,
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale="ru",
            text="<p>Машинный русский</p>",
            source_locale="en",
            source_hash=compute_source_hash(ENGLISH, locale="en"),
        )
        db.commit()
        specs = entity_field_specs(db, "chapter_block", block, "ru")
        assert specs[0].text == ENGLISH
        assert specs[0].source_locale == "en"
        assert course is not None

    def test_a_hand_translation_does_not_move_the_source(self, db: Session) -> None:
        # Two human rows: the original and someone's hand translation.
        # The declared locale wins, so the field is planned from the same
        # language on every tick rather than alternating.
        _course, block = _russian_course_with_a_block(db, text=ENGLISH, locale="en")
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale="ru",
            text=RUSSIAN,
        )
        db.commit()
        first = entity_field_specs(db, "chapter_block", block, "ru")[0]
        second = entity_field_specs(db, "chapter_block", block, "ru")[0]
        assert first.source_locale == second.source_locale == "ru"
        assert first.text == RUSSIAN


class TestACourseThatChangesItsMind:
    def test_flipping_the_declared_language_does_not_orphan_the_tree(self, db: Session) -> None:
        """A separate defect, closed by the same change.

        ``update_course`` re-runs the language detector on every title or
        description edit and reassigns ``course.source_locale``. While
        source text was read at the declared locale, one such edit
        orphaned every cv-backed entity under the course at once: their
        rows sat at the old locale, the walk asked for the new one, and
        the whole tree stopped being planned and stopped being required.
        Reading the author's row wherever it is filed makes the declared
        locale a tie-break rather than a key, so the tree survives its
        course changing its mind.
        """
        course, block = _russian_course_with_a_block(db, text=RUSSIAN, locale="ru")
        before = {task.target_locale for task in plan_course_tasks(db, course) if task.entity_id == str(block.id)}
        assert before == {"en", "de", "uk"}

        course.source_locale = "en"
        db.commit()

        after = {task.target_locale for task in plan_course_tasks(db, course) if task.entity_id == str(block.id)}
        assert after == {"en", "de", "uk"}, "the block is still Russian, whatever the course now says"
        gaps = {
            gap.locale for gap in course_translation_completeness(db, course).gaps if gap.entity_id == str(block.id)
        }
        assert gaps == {"en", "de", "uk"}
