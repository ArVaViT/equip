# ruff: noqa: RUF001
"""A stored translation reused for a second row was never re-pointed.

Read out of production on 2026-08-21. Three chapter blocks hold the
byte-identical German `“Doch weil ihr an Christi Leiden teilhabt…habt.“`
— the closing mark at both ends — with the same three md5s for German,
English and Ukrainian across all three:

    9005ef2e  2026-08-20 23:49:07Z   de 4872dfef  en 08647e9b  uk 6a1fc563
    6354e77f  2026-08-21 19:16:50Z   de 4872dfef  en 08647e9b  uk 6a1fc563
    8792f146  2026-08-21 19:22:50Z   de 4872dfef  en 08647e9b  uk 6a1fc563

The first of those is 21 minutes older than #1123, the commit that
taught `normalize_typography` that a `<blockquote>` is a fresh place for
a quotation to open. The other two were written nineteen hours *after*
it was deployed, and are the same bytes — because they were never
translated. `_load_twins` found the older row, `_decide` handed its text
back as this row's answer, and `execute_plan` wrote it. No provider call,
so no typography: the pass that points a translation is the last thing
`GeminiProvider.translate_within` does, and a copy never goes near it.

The same block quoting Acts 1:8 came back correctly pointed in the same
walkthrough, which is what made this look like an edit-path defect. It
is not. That row's twin had been superseded when the block's content
moved on, so `_load_twins` — which reads only live rows — missed it and
the model was asked. Twin hit and twin miss, in the same course, a
minute apart; the live store loses the marks exactly as the staged one
does, which is what the last test here pins.

Why this is not repaired by raising `TRANSLATOR_VERSION`: measured over
the whole live corpus on 2026-08-21, 6 of 6,128 current-generation
machine rows are mis-pointed, and all 6 are the three copies of this one
block. A bump re-translates six thousand rows to correct six.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, NoReturn

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion
from app.models.course import Course, CourseStatus
from app.models.user import User
from app.services.content_versions.write import record_mt_version
from app.services.translation.executor import TranslationTask, execute_plan
from app.services.translation.hash import compute_source_hash
from app.services.translation.service import reset_translation_provider_cache
from app.services.translation.stores import LIVE_STORE, StagedStore

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RU = (
    "<h3>Радость посреди огня</h3>"
    "<p>Пётр пишет рассеянным церквам не о победе — о надежде (1 Пет. 4:13).</p>"
    "<blockquote>«Но как вы участвуете в Христовых страданиях, радуйтесь»</blockquote>"
)

#: What production holds for this block in German, byte for byte.
DE_AS_STORED = (
    "<h3>Freude inmitten des Feuers</h3>"
    "<p>Petrus schreibt an die verstreuten Gemeinden nicht über Sieg (1. Petr. 4,13).</p>"
    "<blockquote>“Doch weil ihr an Christi Leiden teilhabt, freut euch.“</blockquote>"
)

UK_AS_STORED = (
    "<h3>Радість посеред вогню</h3>"
    "<p>Петро пише розсіяним церквам не про перемогу (1 Петра 4:13).</p>"
    "<blockquote>»А як ви берете участь у Христових стражданнях, радійте»</blockquote>"
)


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


class _MustNotBeAsked:
    """A provider that fails the test if the twin lookup did not answer.

    Reuse is the behaviour being protected here, not the thing being
    fixed: 27% of the corpus is duplicate source text, and asking again
    for each copy is what the twin table exists to stop.
    """

    name = "must-not-be-asked"

    def translate(self, request: object) -> NoReturn:
        raise AssertionError("the stored twin should have answered this task")


def _task(entity_id: str, *, target: str) -> TranslationTask:
    return TranslationTask(
        entity_type="chapter_block",
        entity_id=entity_id,
        field="content",
        source_locale="ru",
        target_locale=target,  # type: ignore[arg-type]
        text=RU,
        content_kind="html",
        source_hash=compute_source_hash(RU, locale="ru"),
    )


def _already_translated(db: Session, entity_id: str, *, locale: str, text: str) -> None:
    """The row a later block will be given a copy of.

    Machine-made by the pipeline in force — that is the only kind
    ``_load_twins`` will reuse, and it is exactly the state production
    was in: written under generation 10, before the generation-10 fix.
    """
    record_mt_version(
        db,
        entity_type="chapter_block",
        entity_id=entity_id,
        field="content",
        locale=locale,
        text=text,
        source_locale="ru",
        source_hash=compute_source_hash(RU, locale="ru"),
    )
    db.commit()


def _a_published_course(db: Session) -> Course:
    """A staged row belongs to a course by foreign key, so the staged
    half of this file needs a real one."""
    teacher = db.query(User).filter(User.role == "teacher").first()
    if teacher is None:
        teacher = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex}@example.com", full_name="T", role="teacher")
        db.add(teacher)
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=teacher.id,
    )
    db.add(course)
    db.commit()
    return course


def _written(db: Session, entity_id: str, locale: str) -> str:
    row = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == "content",
            ContentVersion.locale == locale,
            ContentVersion.superseded_by.is_(None),
        )
        .one()
    )
    return row.text or ""


def _marks(text: str) -> list[str]:
    return [char for char in text if char in '«»„“”"']


class TestACopiedTranslationIsStillPointed:
    def test_the_german_block_from_production_gets_its_opening_mark(self, db: Session) -> None:
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        _already_translated(db, first, locale="de", text=DE_AS_STORED)

        result = execute_plan(db, [_task(second, target="de")], provider=_MustNotBeAsked(), store=LIVE_STORE)

        assert result.translated == 1, "the twin still answers — no second call for the same string"
        assert _marks(_written(db, second, "de")) == ["„", "“"]

    def test_the_ukrainian_block_from_production_gets_its_opening_mark(self, db: Session) -> None:
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        _already_translated(db, first, locale="uk", text=UK_AS_STORED)

        execute_plan(db, [_task(second, target="uk")], provider=_MustNotBeAsked(), store=LIVE_STORE)

        assert _marks(_written(db, second, "uk")) == ["«", "»"]

    def test_a_twin_that_is_already_pointed_is_copied_word_for_word(self, db: Session) -> None:
        """The pass is idempotent, so a row written by the pipeline as it
        stands today is copied unchanged. Pinned because the fix must be
        a repair of what the copy skipped and not an edit of what the
        provider decided."""
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        pointed = DE_AS_STORED.replace("“Doch", "„Doch")
        _already_translated(db, first, locale="de", text=pointed)

        execute_plan(db, [_task(second, target="de")], provider=_MustNotBeAsked(), store=LIVE_STORE)

        assert _written(db, second, "de") == pointed

    def test_the_staged_store_was_never_the_difference(self, db: Session) -> None:
        """The walkthrough that found this read the defect on an edited
        block and the correct marks on a published one, which points at
        the staging table. It is not there. A copy loses its marks
        wherever it lands, because the losing happens before either
        store is asked."""
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        _already_translated(db, first, locale="de", text=DE_AS_STORED)
        store = StagedStore(str(_a_published_course(db).id))

        execute_plan(db, [_task(second, target="de")], provider=_MustNotBeAsked(), store=store)

        row = store.active_row(db, entity_type="chapter_block", entity_id=second, field="content", locale="de")
        assert row is not None and row.text is not None
        assert _marks(row.text) == ["„", "“"]
