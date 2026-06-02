"""Unit tests for the pure-helper functions inside
``app.services.daily_challenge.orchestrator``.

The main orchestrator integration tests in
``test_daily_challenge_orchestrator.py`` exercise the end-to-end
multi-round generation flow and stub ``GeminiPromptClient.invoke``.
That coverage skips the small helper functions that fan-out from the
main flow — scripture validation, verse-range formatting, round-runner
error handling, and review-index resolution. Pin them here so a
refactor of the helpers shows up in CI before it breaks production.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from app.services.daily_challenge import orchestrator as orch
from app.services.daily_challenge.llm import LLMError

if TYPE_CHECKING:
    import pytest


class TestVerseRangeClause:
    """The clause that gets baked into prompts like ``Genesis 3 verses
    1-5`` vs ``Genesis 3 verses 1`` vs no clause when the caller didn't
    pin a verse range. The shape matters — Gemini sees these strings
    and they shouldn't drift."""

    def test_no_verse_from_returns_empty(self) -> None:
        """``verse_from=None`` means the caller wants the whole chapter;
        the prompt-side clause is empty."""
        assert orch._verse_range_clause(None, None) == ""
        # ``verse_to`` is ignored when ``verse_from`` is missing.
        assert orch._verse_range_clause(None, 5) == ""

    def test_single_verse_renders_singular(self) -> None:
        assert orch._verse_range_clause(3, None) == " verses 3"
        # ``verse_to == verse_from`` collapses to the same single-verse form.
        assert orch._verse_range_clause(3, 3) == " verses 3"

    def test_range_renders_with_hyphen(self) -> None:
        assert orch._verse_range_clause(1, 5) == " verses 1-5"
        assert orch._verse_range_clause(10, 15) == " verses 10-15"


class TestFindReviewForIndex:
    """The orchestrator pairs survivors with reviews by index. The
    model sometimes labels the review with ``survivor_index``,
    sometimes with ``candidate_index``, sometimes neither. The lookup
    must handle all three plus the edge case where the list is shorter
    than the index."""

    def test_matches_by_survivor_index(self) -> None:
        reviews = [
            {"survivor_index": 1, "verdict": "pass"},
            {"survivor_index": 0, "verdict": "reject"},
        ]
        assert orch._find_review_for_index(reviews, 0) == {"survivor_index": 0, "verdict": "reject"}

    def test_matches_by_candidate_index(self) -> None:
        reviews = [
            {"candidate_index": 0, "verdict": "pass"},
            {"candidate_index": 1, "verdict": "reject"},
        ]
        assert orch._find_review_for_index(reviews, 1) == {"candidate_index": 1, "verdict": "reject"}

    def test_falls_back_to_positional_when_no_index_field(self) -> None:
        """The model dropped the ``*_index`` field — we use positional
        ordering as the last resort so the orchestrator can still pair
        survivors with reviews."""
        reviews = [{"verdict": "pass"}, {"verdict": "reject"}]
        assert orch._find_review_for_index(reviews, 1) == {"verdict": "reject"}

    def test_skips_non_dict_entries(self) -> None:
        """A model dropping a string into the reviews list (bad JSON
        shape) must not crash the matcher."""
        reviews = ["bogus", {"survivor_index": 0, "verdict": "pass"}]
        assert orch._find_review_for_index(reviews, 0) == {"survivor_index": 0, "verdict": "pass"}

    def test_idx_out_of_bounds_returns_empty_dict(self) -> None:
        """Pin the empty-dict fallback so callers can safely
        ``.get('verdict', 'pass')`` without an isinstance check first."""
        assert orch._find_review_for_index([], 0) == {}
        assert orch._find_review_for_index([{"verdict": "pass"}], 5) == {}

    def test_positional_index_with_non_dict_returns_empty(self) -> None:
        """If positional fallback lands on a non-dict entry the matcher
        gives up rather than crashing the caller's ``.get`` chain."""
        reviews = ["bogus", "also bogus"]
        assert orch._find_review_for_index(reviews, 1) == {}


class TestRunRound:
    """One Gemini call wrapped to map ``LLMError`` into a sentinel
    ``{"_error": "..."}`` dict. The orchestrator inspects ``_error``
    rather than try/except itself so multiple rounds can be threaded
    cleanly without nested exception handlers."""

    def test_happy_path_returns_response(self) -> None:
        client = MagicMock()
        client.invoke.return_value = {"reviews": [{"verdict": "pass"}]}
        out = orch._run_round(
            client,
            system="sys",
            user="user",
            temperature=0.5,
            agent_label="test-round",
        )
        assert out == {"reviews": [{"verdict": "pass"}]}
        # The invoke call carries the parameters as kwargs.
        kwargs = client.invoke.call_args.kwargs
        assert kwargs["system"] == "sys"
        assert kwargs["user"] == "user"
        assert kwargs["temperature"] == 0.5
        assert kwargs["expect_json"] is True

    def test_llm_error_returns_sentinel_dict(self) -> None:
        """``LLMError`` MUST map to ``{"_error": ...}`` so the
        orchestrator can detect-and-continue. Raising would tear down
        the whole multi-round flow."""
        client = MagicMock()
        client.invoke.side_effect = LLMError("rate limited")
        out = orch._run_round(
            client,
            system="s",
            user="u",
            temperature=0.5,
            agent_label="failing-round",
        )
        assert isinstance(out, dict)
        assert "_error" in out
        assert "rate limited" in out["_error"]


class TestSerializeForPrompt:
    """The dict→JSON renderer used to embed structured data into
    user prompts. Must keep Russian text in BMP form (not
    ``\\uXXXX`` escapes) so the model sees the human-readable text."""

    def test_keeps_cyrillic_human_readable(self) -> None:
        rendered = orch._serialize_for_prompt({"text": "Привет, мир"})
        assert "Привет, мир" in rendered
        # Defensive: no ``\u`` escape leaks through.
        assert "\\u" not in rendered

    def test_serialises_nested_structure(self) -> None:
        payload = {"survivors": [{"q": "Q1"}, {"q": "Q2"}]}
        rendered = orch._serialize_for_prompt(payload)
        assert "Q1" in rendered
        assert "Q2" in rendered


class TestValidateCandidateScripture:
    """Stage 2 validation: the cited verse must exist in both KJV and
    Synodal. Returns ``(passed, reason)`` so the orchestrator can log
    a useful rejection reason rather than a generic 'failed' marker."""

    def test_missing_verse_start_rejects(self) -> None:
        passed, reason = orch._validate_candidate_scripture({"verse_start": None}, "Romans", 8)
        assert passed is False
        assert reason is not None
        assert "verse_start" in reason

    def test_negative_verse_start_rejects(self) -> None:
        passed, reason = orch._validate_candidate_scripture({"verse_start": -3}, "Romans", 8)
        assert passed is False
        assert reason is not None
        assert "verse_start" in reason

    def test_zero_verse_start_rejects(self) -> None:
        """Edge case — chapter:verse 0 is never valid scripture."""
        passed, _reason = orch._validate_candidate_scripture({"verse_start": 0}, "Romans", 8)
        assert passed is False

    def test_invalid_verse_end_type_rejects(self) -> None:
        """``verse_end`` is optional, but when present it must be int.
        A string slipping through (model hallucinated a range like
        '5-7') means the slug we cite won't match the source text."""
        passed, reason = orch._validate_candidate_scripture(
            {"verse_start": 1, "verse_end": "five"},
            "Romans",
            8,
        )
        assert passed is False
        assert reason is not None
        assert "verse_end" in reason

    def test_unknown_book_rejects(self) -> None:
        passed, reason = orch._validate_candidate_scripture(
            {"verse_start": 1},
            "BookOfMadeUp",
            1,
        )
        assert passed is False
        assert reason is not None
        assert "unknown book" in reason

    def test_lookup_miss_in_english_rejects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When ``find_book`` resolves but ``lookup`` returns ``None``
        for English, we surface the KJV miss explicitly so a reviewer
        knows the rejection is a bible-coverage gap, not a model
        hallucination."""
        monkeypatch.setattr(orch, "find_book", lambda _b: "rom")

        def fake_lookup(_ref: Any, locale: str) -> Any:
            return None if locale == "en" else "Russian text"

        monkeypatch.setattr(orch, "lookup", fake_lookup)
        passed, reason = orch._validate_candidate_scripture({"verse_start": 5}, "Romans", 8)
        assert passed is False
        assert reason is not None
        assert "KJV" in reason

    def test_lookup_miss_in_russian_rejects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Synodal coverage gap — same kind of explicit failure."""
        monkeypatch.setattr(orch, "find_book", lambda _b: "rom")

        def fake_lookup(_ref: Any, locale: str) -> Any:
            return "English text" if locale == "en" else None

        monkeypatch.setattr(orch, "lookup", fake_lookup)
        passed, reason = orch._validate_candidate_scripture({"verse_start": 5}, "Romans", 8)
        assert passed is False
        assert reason is not None
        assert "Synodal" in reason

    def test_both_lookups_pass_returns_true_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(orch, "find_book", lambda _b: "rom")
        monkeypatch.setattr(orch, "lookup", lambda _r, _l: "some text")
        passed, reason = orch._validate_candidate_scripture({"verse_start": 1, "verse_end": 3}, "Romans", 8)
        assert passed is True
        assert reason is None
