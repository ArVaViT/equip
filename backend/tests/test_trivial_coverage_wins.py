"""Trivial coverage wins discovered in the 2026-06-02 audit.

Bundles 5 quick-to-test gaps that each close 1-3 missing-line
statements with no fixture setup. See
[[reference-equip-easy-backend-coverage-targets]] for the punch list
this implements.

* ``app.api.v1.health`` SQLAlchemyError path on /db
* ``app.services.content_versions.dual_write`` short-circuits
* ``app.services.quiz_service.ensure_attempts_available`` no-limit
* ``app.services.course_readiness`` `_has_meaningful_content` /
  `_question_is_complete` defensive branches
* ``app.models.course`` `__repr__` methods (Course / Module / Chapter)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.models.course import Chapter, Course, Module
from app.services.content_versions.dual_write import (
    _coerce_uuid,
    dual_write_entity_content,
)
from app.services.course_readiness import (
    _has_meaningful_content,
    _question_is_complete,
)
from app.services.quiz_service import ensure_attempts_available

if TYPE_CHECKING:
    import pytest
    from fastapi.testclient import TestClient


class TestHealthDbSqlAlchemyError:
    def test_db_health_503_on_sqlalchemy_error(
        self,
        admin_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the SELECT 1 probe raises ``SQLAlchemyError`` the route
        catches it and returns 503 with the canonical envelope, not
        a 500 with a stack trace."""

        def fake_execute(*_args: object, **_kwargs: object) -> object:
            raise OperationalError("lock timeout", None, Exception("dead"))

        monkeypatch.setattr("sqlalchemy.orm.Session.execute", fake_execute)
        r = admin_client.get("/api/v1/health/db")
        assert r.status_code == 503
        assert "Database connection failed" in r.json()["detail"]["message"]


class TestDualWriteShortCircuits:
    def test_empty_texts_dict_short_circuits(self) -> None:
        """An empty ``texts`` dict skips the whole write path —
        ``record_human_version`` is never invoked."""
        db = MagicMock()
        dual_write_entity_content(
            db,
            entity_type="course",
            entity_id="c-1",
            texts={},
            fallback_locale="en",
        )
        # No record_human_version call would touch ``db.add`` / flush;
        # the mock should see zero query attempts on either.
        db.add.assert_not_called()

    def test_only_fields_filters_to_caller_subset(self) -> None:
        """``only_fields`` restricts the write to the named fields.
        Passing a single-field subset of a multi-key ``texts`` skips
        the others."""
        # Simulate a description-only PATCH: title is in texts but the
        # caller asked us to only write description. The function must
        # see no fields to process (description was None) and bail.
        db = MagicMock()
        dual_write_entity_content(
            db,
            entity_type="course",
            entity_id="c-2",
            texts={"title": "Won't be written"},
            only_fields=["description"],  # title filtered out
            fallback_locale="en",
        )
        db.add.assert_not_called()

    def test_coerce_uuid_string_round_trip(self) -> None:
        """The ``_coerce_uuid`` helper accepts a string and returns
        a real ``UUID`` instance — the column type bind processor on
        ``profiles.id`` needs the real type."""
        u = uuid.uuid4()
        coerced = _coerce_uuid(str(u))
        assert coerced == u
        assert isinstance(coerced, uuid.UUID)

    def test_coerce_uuid_passes_uuid_through(self) -> None:
        u = uuid.uuid4()
        assert _coerce_uuid(u) is u

    def test_coerce_uuid_passes_none(self) -> None:
        assert _coerce_uuid(None) is None

    def test_unclassifiable_text_with_no_fallback_skips_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When detection has no signal for a field's text and the caller
        passed no ``fallback_locale`` either, the field is silently
        skipped — it will retry on the next save with more context —
        rather than writing a row with ``locale=None``."""
        monkeypatch.setattr(
            "app.services.content_versions.dual_write.detect_locale",
            lambda _text: None,
        )
        db = MagicMock()
        # …and the field has no existing human row to inherit a language
        # from either. That lookup is the second of the three answers
        # ``dual_write`` tries before giving up.
        db.query.return_value.filter.return_value.scalar.return_value = None
        dual_write_entity_content(
            db,
            entity_type="course",
            entity_id="c-3",
            texts={"title": "???"},
            fallback_locale=None,
        )
        db.add.assert_not_called()


class TestEnsureAttemptsAvailableNoLimit:
    def test_max_attempts_none_early_returns(self) -> None:
        """A quiz with ``max_attempts=None`` has infinite attempts.
        The helper must short-circuit before querying — passing a
        MagicMock for ``db`` would crash if anything reached for it.
        """
        quiz = MagicMock()
        quiz.max_attempts = None
        # A bare MagicMock for db; if the function tried to query it
        # ``ensure_attempts_available`` would call query/filter/count
        # and we'd see those calls. The assertion below pins the
        # short-circuit.
        db = MagicMock()
        ensure_attempts_available(db, quiz, uuid.uuid4())
        db.query.assert_not_called()


class TestBlockHasContentDefensives:
    def test_non_content_block_type_returns_false(self) -> None:
        """Unknown / quiz / assignment block types short-circuit to
        False before consulting the content-cv set."""
        block = MagicMock()
        block.block_type = "quiz"
        assert _has_meaningful_content(block, blocks_with_cv_content=set()) is False

    def test_file_block_without_file_path_returns_false(self) -> None:
        """A file block with no ``file_path`` isn't publishable."""
        block = MagicMock()
        block.block_type = "file"
        block.file_path = None
        assert _has_meaningful_content(block, blocks_with_cv_content=set()) is False

    def test_file_block_with_file_path_returns_true(self) -> None:
        block = MagicMock()
        block.block_type = "file"
        block.file_path = "/some/path.pdf"
        assert _has_meaningful_content(block, blocks_with_cv_content=set()) is True


class TestQuestionIsCompleteAlwaysTrueTypes:
    def test_essay_always_complete(self) -> None:
        """``essay`` and ``short_answer`` are grader-driven — no
        options needed. The helper returns True regardless of the
        options list."""
        q = MagicMock()
        q.question_type = "essay"
        assert _question_is_complete(q, options=[]) is True

    def test_short_answer_always_complete(self) -> None:
        q = MagicMock()
        q.question_type = "short_answer"
        assert _question_is_complete(q, options=[]) is True


class TestCourseTreeReprs:
    """``__repr__`` methods on Course / Module / Chapter are read by
    log lines and the SQLAlchemy debug printer. Pin the shape so a
    refactor that drops a key doesn't silently regress the log
    grep recipes."""

    def test_course_repr(self) -> None:
        c = Course(id="c-1", source_locale="en", created_by=uuid.uuid4())
        assert "<Course" in repr(c)
        assert "id='c-1'" in repr(c)

    def test_module_repr(self) -> None:
        m = Module(id="m-1", course_id="c-1", order_index=0)
        r = repr(m)
        assert "<Module" in r
        assert "id='m-1'" in r
        assert "course_id='c-1'" in r

    def test_chapter_repr(self) -> None:
        ch = Chapter(
            id="ch-1",
            module_id="m-1",
            title="Hi",
            order_index=0,
            chapter_type="reading",
        )
        r = repr(ch)
        assert "<Chapter" in r
        assert "id='ch-1'" in r
        assert "title='Hi'" in r
        assert "module_id='m-1'" in r
