"""A bibliography survives verbatim because that is what a bibliography does.

``_check_untranslated_run`` blocks a run of ten or more source words,
forty-five or more characters, that reappears word for word in the
translation. ``F. F. Bruce, The Book of the Acts, Grand Rapids:
Eerdmans, 1988`` is twelve words and sixty-odd characters, it *should*
reappear word for word in a German lesson, and on 2026-08-19 it came
back ``untranslated_run`` with ``blocking=True``. A church-history or
OT-survey course is a list of these, and a blocking issue parks the row
at ``needs_review`` where ``executor`` skips it for as long as the
source hash is unchanged — so one reading list retires a course.

Why the check was demoted rather than narrowed
----------------------------------------------
The obvious narrowing is to ignore a run that sits entirely inside
quotation marks, italics or parentheses. It was rejected twice over.
The founding incident this check exists for *was* a quotation — a German
sentence wrapping an English verse in quotes — and rule 2b of the system
prompt now says outright that quotation marks are not a
do-not-translate sign, so the region a citation hides in is the region
an untranslated verse hides in and nothing in the shape of the text
separates them. And it would not have helped here anyway: a
bibliography line in a plain ``<li>`` carries no quotes, no italics and
no parentheses.

So the check keeps its eyes and loses its veto. Non-blocking still buys
the remedy that fixes most of these — ``executor._ask`` shows the model
the run it left behind and asks again — and still logs a stable code
somebody can count. What it no longer does is withhold the page.
"""

from __future__ import annotations

from app.services.translation.validation import ValidationIssue, validate_translation

CITATION = "F. F. Bruce, The Book of the Acts, Grand Rapids: Eerdmans, 1988"


def codes(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues}


def blocking(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues if issue.blocking}


class TestABibliographyDoesNotParkALesson:
    def test_a_plain_list_item_carries_no_quotes_or_italics_and_still_passes(self):
        issues = validate_translation(
            source=f"<p>For further reading on this question:</p><ul><li>{CITATION}</li></ul>",
            translated=f"<p>Zur Vertiefung dieser Frage:</p><ul><li>{CITATION}</li></ul>",
            source_locale="en",
            target_locale="de",
            content_kind="html",
        )
        assert blocking(issues) == set()

    def test_the_same_citation_in_italics_passes(self):
        issues = validate_translation(
            source=f"<p>For further reading on this question:</p><p><em>{CITATION}</em></p>",
            translated=f"<p>Zur Vertiefung dieser Frage:</p><p><em>{CITATION}</em></p>",
            source_locale="en",
            target_locale="uk",
            content_kind="html",
        )
        assert blocking(issues) == set()


class TestTheDefectItWasBuiltForIsStillReported:
    def test_a_verse_left_in_the_source_language_is_still_named(self):
        # The founding incident: German prose wrapping an English verse.
        # Still detected, still fed to the correcting retry — only no
        # longer able to park the row.
        source = (
            "John 3:17 states, 'For God did not send his Son into the world to condemn "
            "the world, but in order that the world might be saved through him.'"
        )
        translated = (
            "Johannes 3,17 besagt: 'For God did not send his Son into the world to condemn "
            "the world, but in order that the world might be saved through him.'"
        )
        issues = validate_translation(
            source=source,
            translated=translated,
            source_locale="en",
            target_locale="de",
        )
        assert "untranslated_run" in codes(issues)

    def test_and_the_model_is_told_what_to_do_about_it(self):
        # ``executor._ask`` passes ``issue.detail`` back to the provider
        # as a rewrite note, so the sentence has to be usable as one.
        source = (
            "John 3:17 states, 'For God did not send his Son into the world to condemn "
            "the world, but in order that the world might be saved through him.'"
        )
        translated = (
            "Johannes 3,17 besagt: 'For God did not send his Son into the world to condemn "
            "the world, but in order that the world might be saved through him.'"
        )
        issues = validate_translation(
            source=source,
            translated=translated,
            source_locale="en",
            target_locale="de",
        )
        note = next(issue.detail for issue in issues if issue.code == "untranslated_run")
        assert "survives verbatim" in note
        assert "bibliographic citation" in note


class TestSomethingStillWithholdsAWhollyUntranslatedBlock:
    """Demoting one check does not mean an untranslated lesson ships. The
    whole-string checks are the backstop, and they still block."""

    def test_a_paragraph_that_came_back_as_it_went_in_is_blocked(self):
        paragraph = "<p>The apostle Paul wrote this letter to the church in Corinth around the year 55.</p>"
        issues = validate_translation(
            source=paragraph,
            translated=paragraph,
            source_locale="en",
            target_locale="de",
            content_kind="html",
        )
        assert "not_translated" in blocking(issues)

    def test_a_paragraph_answered_in_the_source_language_is_blocked(self):
        issues = validate_translation(
            source="<p>The apostle Paul wrote this letter to the church in Corinth around the year 55.</p>",
            translated="<p>The apostle Paul wrote this letter to the congregation at Corinth about the year 55.</p>",
            source_locale="en",
            target_locale="de",
            content_kind="html",
        )
        assert "wrong_language" in blocking(issues)
