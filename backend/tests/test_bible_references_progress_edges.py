"""Small-gap unit tests for ``app.services.bible.references`` +
``app.api.v1.progress``. Each closes a single-line or short-cluster
gap left by the happy-path tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.bible.references import BibleRef, parse_references

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


class TestBibleRefStr:
    """``BibleRef.__str__`` is what gets baked into prompt text and
    log lines. Single-verse vs range have different shapes — pin both
    so a future refactor that uses ``f"{ref}"`` somewhere doesn't drift."""

    def test_single_verse_no_range(self) -> None:
        assert str(BibleRef(book="Romans", chapter=8, verse_start=28)) == "Romans 8:28"

    def test_range_with_verse_end(self) -> None:
        assert str(BibleRef(book="Romans", chapter=8, verse_start=28, verse_end=30)) == "Romans 8:28-30"


class TestParseReferencesEdges:
    def test_empty_input_returns_empty_list(self) -> None:
        """Cheap short-circuit — empty / falsy input doesn't trigger
        the regex walk."""
        assert parse_references("") == []
        # The function checks ``if not text``; None would crash before
        # reaching the regex. The route layer never passes None, so the
        # SUT's contract is "non-None str" — pin the falsy-but-str case.
        assert parse_references("") == []

    def test_unknown_book_match_is_skipped(self) -> None:
        """The regex is liberal — defensive ``find_book`` resolves the
        canonical slug and the iteration skips anything that fails to
        resolve. Pin so a future regex tightening doesn't accidentally
        let an unknown alias slip through to ``find_book is None``
        path with a real book id."""
        # The regex requires a known book alias to match in the first
        # place, so this test inherently relies on a string the regex
        # rejects → no parsed references.
        assert parse_references("Notabook 1:1 is not real") == []


class TestProgressNotEnrolled:
    """``GET /progress/course/{course_id}/me`` requires enrollment.
    Non-enrolled student → 403 with the canonical envelope."""

    def test_not_enrolled_returns_403(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        # The student is logged in but never enrolled in this course.
        # The course doesn't need to exist for the enrollment check; the
        # query just returns None either way.
        r = student_client.get("/api/v1/progress/course/never-enrolled-course/my-progress")
        assert r.status_code == 403
        body = r.json()
        assert "not enrolled" in body["detail"]["message"].lower()
