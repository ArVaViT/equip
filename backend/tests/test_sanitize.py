"""Regression tests for ``app.core.sanitize.sanitize_string``.

The block editor emits a small set of HTML constructs that need to
round-trip through bleach without losing semantically important
attributes. The closest existing tests exercise these only through the
block-create / chapter-render API, which makes failures hard to
diagnose. These unit tests pin the sanitizer's behaviour directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core import sanitize as sanitize_mod
from app.core.sanitize import sanitize_string

if TYPE_CHECKING:
    import pytest


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


class TestIframeAllowlist:
    """Iframes are dangerous by default — only YouTube embeds get
    through. Bleach treats ``iframe`` as a normal allowed tag (it
    doesn't know which ``src`` values are safe), so the post-filter in
    ``_strip_dangerous_iframes`` is what actually enforces the embed
    policy. These tests pin both halves of the decision.
    """

    def test_youtube_embed_iframe_survives(self):
        html = (
            '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" width="560" height="315" allowfullscreen></iframe>'
        )
        cleaned = sanitize_string(html)
        assert "<iframe" in cleaned
        assert "youtube.com/embed/dQw4w9WgXcQ" in cleaned

    def test_youtube_nocookie_embed_survives(self):
        # The privacy-enhanced YouTube embed domain (``youtube-nocookie.com``)
        # is the recommended embed form for cookie-conscious sites. The
        # allowlist must accept it alongside the canonical domain.
        html = '<iframe src="https://www.youtube-nocookie.com/embed/abcDEF12345"></iframe>'
        cleaned = sanitize_string(html)
        assert "<iframe" in cleaned
        assert "youtube-nocookie.com/embed/" in cleaned

    def test_non_youtube_iframe_is_stripped(self):
        # The iframe wrapper is removed but the surrounding text stays
        # intact — we strip the dangerous element, we don't blow up the
        # whole block.
        cleaned = sanitize_string('<p>before</p><iframe src="https://evil.example.com/track"></iframe><p>after</p>')
        assert "<iframe" not in cleaned
        assert "evil.example.com" not in cleaned
        assert "<p>before</p>" in cleaned
        assert "<p>after</p>" in cleaned

    def test_iframe_with_no_src_is_stripped(self):
        # An iframe without ``src`` cannot be a YouTube embed by
        # construction — the post-filter treats "no src" as the
        # untrusted case and strips it.
        cleaned = sanitize_string("<iframe></iframe>")
        assert "<iframe" not in cleaned

    def test_iframe_with_single_quoted_src_handled(self):
        # Bleach normalises attribute quoting, but a teacher pasting raw
        # HTML can produce single-quoted attrs. The regex used by the
        # post-filter accepts both quote styles.
        cleaned = sanitize_string("<iframe src='https://www.youtube.com/embed/abc123'></iframe>")
        # After bleach + post-filter the iframe should survive in some
        # canonical form (quotes may be normalised).
        assert "youtube.com/embed/abc123" in cleaned


class TestEarlyReturns:
    """Two zero-cost short-circuit paths in ``sanitize_string`` — both
    skip the whole bleach + regex pipeline. Pin them so a future
    refactor that drops the guard surfaces in CI rather than silently
    starting to allocate per empty-string call.
    """

    def test_empty_string_returns_empty(self):
        assert sanitize_string("") == ""

    def test_none_passes_through_unchanged(self):
        # ``sanitize_string`` is called on Pydantic-validated fields;
        # an explicit ``None`` shouldn't crash on the ``not value``
        # truthiness check — it returns the input as-is.
        assert sanitize_string(None) is None  # type: ignore[arg-type]


class TestRegexFallback:
    """When ``bleach`` is not importable we fall back to a regex strip
    of the worst offenders (scripts, event handlers, javascript: URLs).
    This is the path that runs on bare deploys without the optional
    sanitiser package; the production deploys all ship bleach, but the
    fallback is the safety net.

    The branch is gated on a module-level ``_HAS_BLEACH`` constant set
    at import time, so we monkeypatch the flag directly rather than
    trying to fight the optional dependency at runtime.
    """

    def test_regex_strips_script_tag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sanitize_mod, "_HAS_BLEACH", False)
        cleaned = sanitize_string("<p>hi</p><script>alert(1)</script>")
        assert "<script" not in cleaned
        # The non-dangerous markup is left alone — regex fallback is a
        # blacklist, not the bleach allowlist, so unrelated tags pass
        # through. That's intentional: it's defence-in-depth on top of
        # DOMPurify, not a primary sanitiser.
        assert "<p>hi</p>" in cleaned

    def test_regex_strips_event_handler_attr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sanitize_mod, "_HAS_BLEACH", False)
        cleaned = sanitize_string('<a href="/x" onclick="evil()">x</a>')
        assert "onclick" not in cleaned

    def test_regex_strips_javascript_scheme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sanitize_mod, "_HAS_BLEACH", False)
        cleaned = sanitize_string('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in cleaned

    def test_regex_strips_iframe_meta_link(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sanitize_mod, "_HAS_BLEACH", False)
        cleaned = sanitize_string(
            "<meta http-equiv='refresh' content='0'><link rel='stylesheet' href='evil.css'><style>body{}</style>"
        )
        assert "<meta" not in cleaned
        assert "<link" not in cleaned
        assert "<style" not in cleaned

    def test_regex_path_strips_surrounding_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sanitize_mod, "_HAS_BLEACH", False)
        assert sanitize_string("   hello   ") == "hello"
