"""Regression tests for ``app.core.sanitize.sanitize_string``.

The block editor emits a small set of HTML constructs that need to
round-trip through bleach without losing semantically important
attributes. The closest existing tests exercise these only through the
block-create / chapter-render API, which makes failures hard to
diagnose. These unit tests pin the sanitizer's behaviour directly.
"""

from __future__ import annotations

from app.core.sanitize import sanitize_string


class TestBaseAllowlist:
    def test_plain_text_passes_through(self):
        assert sanitize_string("Hello, world.") == "Hello, world."

    def test_basic_formatting_survives(self):
        html = "<p><strong>Hi</strong> <em>there</em>.</p>"
        assert sanitize_string(html) == html

    def test_script_tag_is_stripped(self):
        assert "<script" not in sanitize_string("<p>hi</p><script>alert(1)</script>")

    def test_event_handlers_are_stripped(self):
        cleaned = sanitize_string('<a href="/x" onclick="alert(1)">click</a>')
        assert "onclick" not in cleaned

    def test_javascript_scheme_is_stripped(self):
        cleaned = sanitize_string('<a href="javascript:alert(1)">x</a>')
        # bleach drops the href attribute when its protocol isn't allowlisted.
        assert "javascript:" not in cleaned


class TestTableAllowlist:
    """The TipTap Table extension emits ``<table>`` + ``<thead>`` /
    ``<tbody>`` / ``<tr>`` / ``<th>`` / ``<td>`` with ``colspan`` and
    ``rowspan`` on merged cells. Without those attrs in the bleach
    allowlist, a teacher who merges cells loses the merge on first save
    — silently, because the visible content stays intact.
    """

    def test_table_skeleton_round_trips(self):
        html = "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
        cleaned = sanitize_string(html)
        assert "<table>" in cleaned
        assert "<thead>" in cleaned
        assert "<tbody>" in cleaned
        assert "<th>A</th>" in cleaned
        assert "<td>1</td>" in cleaned

    def test_colspan_survives_on_td(self):
        cleaned = sanitize_string('<table><tr><td colspan="2">merged</td></tr></table>')
        assert 'colspan="2"' in cleaned

    def test_rowspan_survives_on_td(self):
        cleaned = sanitize_string('<table><tr><td rowspan="3">tall</td></tr></table>')
        assert 'rowspan="3"' in cleaned

    def test_colspan_and_rowspan_survive_on_th(self):
        cleaned = sanitize_string('<table><tr><th colspan="2" rowspan="2">grid</th></tr></table>')
        assert 'colspan="2"' in cleaned
        assert 'rowspan="2"' in cleaned

    def test_th_scope_survives(self):
        cleaned = sanitize_string('<table><tr><th scope="col">Col</th></tr></table>')
        assert 'scope="col"' in cleaned

    def test_inline_style_on_cell_is_stripped(self):
        # ``style`` is not in the allowlist — defence-in-depth against
        # CSS-injection / leak-via-content tricks.
        cleaned = sanitize_string('<table><tr><td style="background: red">x</td></tr></table>')
        assert "style=" not in cleaned

    def test_equip_table_class_survives(self):
        # The frontend TipTap Table extension stamps ``equip-table`` on
        # the outer element so the .prose-cascade CSS can target it
        # without leaking into other tables on the page.
        cleaned = sanitize_string('<table class="equip-table"><tr><td>x</td></tr></table>')
        assert 'class="equip-table"' in cleaned


class TestCodeBlockAllowlist:
    """The CodeBlockLowlight extension emits
    ``<pre><code class="language-X">...</code></pre>`` with highlight.js
    wrapping individual tokens in ``<span class="hljs-Y">``. ``pre`` /
    ``code`` / ``span`` are already allowed tags; this pins ``class``
    survival across the round-trip so a teacher's code samples don't
    lose their syntax highlighting on first save.
    """

    def test_language_class_survives_on_code(self):
        cleaned = sanitize_string('<pre><code class="language-python">print(1)</code></pre>')
        assert 'class="language-python"' in cleaned
        assert "<pre>" in cleaned

    def test_highlight_token_spans_survive(self):
        html = (
            '<pre><code class="language-python">'
            '<span class="hljs-built_in">print</span>'
            '(<span class="hljs-number">1</span>)'
            "</code></pre>"
        )
        cleaned = sanitize_string(html)
        assert 'class="hljs-built_in"' in cleaned
        assert 'class="hljs-number"' in cleaned
