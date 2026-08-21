# ruff: noqa: RUF001
"""Three backticks reached a page students read.

Asked for HTML, the model sometimes answers in a markdown code block —
an opening fence, the markup, a closing fence. The scaffolding unwrapper
next to this one does not see it: that looks for the tokens the prompt
supplied, and this is the model volunteering a convention of its own.

A live Ukrainian lesson body carries an opening fence welded to the end
of a heading and a bare closing one at the end of the block. It passed
every check, because the markup either side is intact and a fence is not
a tag — the tag comparison balances, the language is right, the numbers
survive, and nothing in the pipeline reads a backtick.

Conditioned on the source rather than on the shape of the reply: a
lesson that genuinely teaches markdown carries the fence in the Russian
too, and then it is content, not scaffolding.
"""

from __future__ import annotations

import pytest

from app.services.translation.gemini import GeminiTranslationProvider

_drop = GeminiTranslationProvider._drop_markdown_fence

PRODUCTION_SOURCE = (
    "<p>Итог: книга делится на исторические и пророческие разделы.</p>\n\n"
    "<h2>Проверьте себя</h2>\n"
    '<div class="callout callout-toggle">\n<p><strong>Вопрос.</strong></p>\n</div>'
)
PRODUCTION_REPLY = (
    "<p>Підсумок: книга поділяється на історичні та пророчі розділи.</p>\n\n"
    "<h2>Перевірте себе</h2>```html\n"
    '<div class="callout callout-toggle">\n<p><strong>Питання.</strong></p>\n</div>\n```'
)


class TestAFenceTheAuthorNeverWrote:
    def test_the_production_row_comes_back_without_its_backticks(self) -> None:
        cleaned = _drop(PRODUCTION_REPLY, PRODUCTION_SOURCE)
        assert "```" not in cleaned

    def test_and_nothing_else_about_it_moves(self) -> None:
        """The fence goes; the lesson does not. Every tag and every word
        the model wrote is still there in the same order."""
        cleaned = _drop(PRODUCTION_REPLY, PRODUCTION_SOURCE)
        assert "<h2>Перевірте себе</h2>" in cleaned
        assert '<div class="callout callout-toggle">' in cleaned
        assert "Питання" in cleaned
        assert cleaned.replace("\n", "") == PRODUCTION_REPLY.replace("```html", "").replace("```", "").replace("\n", "")

    @pytest.mark.parametrize("fence", ["```", "```html", "```HTML", "  ```json  "])
    def test_any_shape_of_fence_marker_goes(self, fence: str) -> None:
        reply = f"{fence}\n<p>Text</p>\n```"
        assert "```" not in _drop(reply, "<p>Текст</p>")


class TestWhatMustSurvive:
    def test_a_lesson_that_teaches_markdown_keeps_its_fence(self) -> None:
        """The condition that makes this safe. If the author wrote a
        fence, it is the subject of the lesson and not scaffolding —
        removing it would be the pipeline editing content."""
        source = "<p>Код оформляется так:</p>\n```\nprint('hi')\n```"
        reply = "<p>Code is written like this:</p>\n```\nprint('hi')\n```"
        assert _drop(reply, source) == reply

    def test_a_reply_with_no_fence_is_returned_unchanged(self) -> None:
        reply = "<p>Nothing to do here.</p>"
        assert _drop(reply, "<p>Тут нечего делать.</p>") is reply

    def test_a_stray_backtick_pair_inside_prose_is_left_alone(self) -> None:
        """The marker is matched on its own line. A pair of backticks
        used inline is punctuation, not a fence, and this pass has no
        business touching it."""
        reply = "<p>The word ``Sabbath`` appears twice.</p>"
        assert _drop(reply, "<p>Слово ``суббота`` встречается дважды.</p>") == reply

    def test_removing_a_fence_twice_changes_nothing_the_second_time(self) -> None:
        once = _drop(PRODUCTION_REPLY, PRODUCTION_SOURCE)
        assert _drop(once, PRODUCTION_SOURCE) == once
