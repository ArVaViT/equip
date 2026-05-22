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


class TestMathMarkerAllowlist:
    """The TipTap math extension stores math as
    ``<span data-type="inlineMath" data-latex="..." data-display="...">
    $x^2$</span>``. The BlockRenderer re-runs ``katex.render`` over each
    marker at view time, so the data-* attributes must round-trip
    through bleach intact — otherwise the chapter view shows the raw
    ``$x^2$`` delimiters instead of the rendered formula.

    (The extension can also emit ``data-evaluate`` for symbolic-math
    evaluation, but we configure ``evaluation: false`` on the frontend
    so the attribute never ships. It is *not* in the sanitiser
    allowlist — see ``test_data_evaluate_attr_is_stripped``.)
    """

    def test_inline_math_marker_survives(self):
        html = (
            '<p>Theorem: <span data-type="inlineMath" data-latex="a^2+b^2=c^2" '
            'data-display="no">$a^2+b^2=c^2$</span>.</p>'
        )
        cleaned = sanitize_string(html)
        assert 'data-type="inlineMath"' in cleaned
        assert 'data-latex="a^2+b^2=c^2"' in cleaned
        assert 'data-display="no"' in cleaned

    def test_block_math_marker_survives(self):
        html = (
            '<p><span data-type="inlineMath" data-latex="\\sum_{i=0}^n i" '
            'data-display="yes">$$\\sum_{i=0}^n i$$</span></p>'
        )
        cleaned = sanitize_string(html)
        assert 'data-display="yes"' in cleaned
        assert "\\sum_{i=0}^n i" in cleaned

    def test_data_evaluate_attr_is_stripped(self):
        # The math extension is configured ``evaluation: false`` so it
        # never emits ``data-evaluate``. We don't allowlist it; assert
        # it stays stripped so a future re-enable of the symbolic
        # evaluator is a deliberate two-step decision (frontend config
        # + sanitiser allowlist), not an accidental leak.
        cleaned = sanitize_string(
            '<span data-type="inlineMath" data-latex="1+2" data-display="no" data-evaluate="yes">$1+2$</span>'
        )
        assert "data-evaluate" not in cleaned
        # The legitimate attrs still survive.
        assert 'data-type="inlineMath"' in cleaned

    def test_other_span_attrs_still_stripped(self):
        # Defence-in-depth: a malicious span carrying a non-allowlisted
        # data-* attribute (or a real event handler) must still be
        # scrubbed even after we widened the span allowlist for math.
        cleaned = sanitize_string('<span data-evil="payload" onclick="x">x</span>')
        assert "data-evil" not in cleaned
        assert "onclick" not in cleaned


class TestToggleCalloutAllowlist:
    """The TipTap Callout ``toggle`` variant stores as
    ``<div data-callout="toggle">``; the chapter view rewrites that to a
    native ``<details><summary>...`` at render time (see
    ``frontend/src/lib/callout-toggle.ts``). Both shapes must round-trip
    through bleach intact — the div shape so the editor can re-load
    saved content, the ``<details>`` shape so a teacher who pastes the
    rendered HTML back (or a future server-side renderer that pre-bakes
    it) keeps the click-to-expand affordance.
    """

    def test_div_storage_shape_survives(self):
        html = (
            '<div data-callout="toggle" class="callout callout-toggle">'
            "<p>What is grace?</p><p>Unmerited favor.</p></div>"
        )
        cleaned = sanitize_string(html)
        assert 'data-callout="toggle"' in cleaned
        assert 'class="callout callout-toggle"' in cleaned
        assert "<p>What is grace?</p>" in cleaned

    def test_details_summary_render_shape_survives(self):
        html = (
            '<details data-callout="toggle" class="callout callout-toggle" open>'
            "<summary>What is grace?</summary>"
            "<p>Unmerited favor.</p></details>"
        )
        cleaned = sanitize_string(html)
        assert "<details" in cleaned
        assert "<summary>What is grace?</summary>" in cleaned
        # ``open`` is a boolean HTML attribute — bleach normalises it to
        # ``open`` or ``open=""``; assert the attribute is present on the
        # element itself rather than just somewhere in the string.
        assert "<details" in cleaned and (" open>" in cleaned or 'open=""' in cleaned)

    def test_details_without_open_attr_stays_collapsed(self):
        # Teachers default to collapsed toggles; the ``open`` attr only
        # appears when explicitly set. Make sure bleach doesn't inject
        # it as a side effect of widening the allowlist.
        cleaned = sanitize_string('<details data-callout="toggle"><summary>q</summary><p>a</p></details>')
        assert "open" not in cleaned

    def test_details_strips_event_handlers(self):
        # Defence-in-depth — ``ontoggle`` would fire on every expand, so
        # widening the allowlist for ``details`` must not let it slip in.
        cleaned = sanitize_string(
            '<details data-callout="toggle" ontoggle="alert(1)" open><summary>x</summary><p>y</p></details>'
        )
        assert "ontoggle" not in cleaned
        assert "alert" not in cleaned
