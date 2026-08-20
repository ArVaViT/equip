"""A lesson block that is nothing but a code sample is already in every language.

Rule 7 of the system prompt tells the model to return text that is
already in the target language unchanged, and a SQL statement or a
Python loop qualifies. The model obeys, and two blocking checks then
punish it for obeying: ``_check_identity`` sees output identical to
input, and ``_check_language`` asks a detector that reads
``SELECT * FROM courses`` and ``for i in range(10)`` as fluent English.

Verified on 2026-08-19 against the real validator: a code-only block
ru→de returned ``[('not_translated', True), ('wrong_language', True)]``.
Two blocking issues park the row at ``needs_review``, ``executor`` skips
a parked row whose source hash has not moved, and the reconciler then
reads the course as waiting on a person.

The judgement both checks make is about prose. Once the code spans and
the markup are stripped — by ``_words_for_runs``, which the untranslated
-run check already used for the same reason — a block with no words left
is not a translation that failed. It is a block with nothing in it to
judge. Everything else about it is still checked: markers, tags,
placeholders, length.
"""

from __future__ import annotations

from app.services.translation.validation import ValidationIssue, validate_translation

CODE_BLOCK = "<pre><code>SELECT * FROM courses;\nfor i in range(10):\n    print(i)\n</code></pre>"


def codes(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues}


def blocking(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues if issue.blocking}


class TestCodeIsNotAFailedTranslation:
    def test_a_block_that_is_only_code_passes(self):
        issues = validate_translation(
            source=CODE_BLOCK,
            translated=CODE_BLOCK,
            source_locale="ru",
            target_locale="de",
            content_kind="html",
        )
        assert blocking(issues) == set()

    def test_an_inline_code_span_without_a_pre_wrapper_passes(self):
        # Not every code sample arrives wrapped in ``<pre>``. The
        # detector reads the letters either way.
        block = "<p><code>SELECT title, locale FROM content_versions WHERE status = 'ok';</code></p>"
        issues = validate_translation(
            source=block,
            translated=block,
            source_locale="ru",
            target_locale="de",
            content_kind="html",
        )
        assert blocking(issues) == set()

    def test_the_rest_of_the_checks_still_run_on_it(self):
        # Declining to judge the language is not declining to judge the
        # block. A code sample that came back with half its markup gone
        # is still a defect.
        issues = validate_translation(
            source=CODE_BLOCK,
            translated="<pre>SELECT * FROM courses;</pre>",
            source_locale="ru",
            target_locale="de",
            content_kind="html",
        )
        assert "markup_mismatch" in blocking(issues)


class TestProseIsStillJudged:
    def test_a_paragraph_returned_unchanged_is_still_not_translated(self):
        prose = "<p>Апостол Павел написал это послание церкви в Коринфе около 55 года.</p>"
        issues = validate_translation(
            source=prose,
            translated=prose,
            source_locale="ru",
            target_locale="de",
            content_kind="html",
        )
        assert "not_translated" in blocking(issues)

    def test_a_paragraph_answered_in_the_wrong_language_is_still_caught(self):
        issues = validate_translation(
            source="<p>Апостол Павел написал это послание церкви в Коринфе около 55 года.</p>",
            translated="<p>The apostle Paul wrote this letter to the church in Corinth around the year 55.</p>",
            source_locale="ru",
            target_locale="de",
            content_kind="html",
        )
        assert "wrong_language" in blocking(issues)

    def test_prose_wrapped_around_a_code_sample_is_still_judged(self):
        # The gate asks whether *anything* is left after the code comes
        # out, not whether code is present. A sentence beside the sample
        # is a sentence, and returning it unchanged is still a defect.
        prose = f"<p>Апостол Павел написал это послание церкви в Коринфе около 55 года.</p>{CODE_BLOCK}"
        issues = validate_translation(
            source=prose,
            translated=prose,
            source_locale="ru",
            target_locale="de",
            content_kind="html",
        )
        assert "not_translated" in blocking(issues)
