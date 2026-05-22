import katex from "katex";

/**
 * Walks ``container`` for math markers emitted by
 * ``@aarkue/tiptap-math-extension`` and replaces each marker's text
 * content with the KaTeX-rendered HTML output.
 *
 * The TipTap extension only renders math via a NodeView inside the
 * editor. For chapter pages (``BlockRenderer``) the stored HTML is
 * piped through ``dangerouslySetInnerHTML`` — KaTeX never runs unless
 * we call it explicitly, leaving the student staring at the raw
 * ``$x^2$`` source.
 *
 * The extension stores math as:
 *   ``<span data-type="inlineMath" data-latex="x^2" data-display="no">$x^2$</span>``
 *
 * We render LaTeX from ``data-latex`` (not the inner text, which has
 * the delimiters baked in) and replace the span's children with the
 * KaTeX output. Idempotent — markers that have already been rendered
 * carry a ``data-katex-rendered`` flag we skip on the second pass.
 *
 * Throws are caught per-marker: a single malformed expression must
 * never blank out the rest of the chapter.
 */
export function renderMathIn(container: HTMLElement | null): void {
  if (!container) return;
  const nodes = container.querySelectorAll<HTMLSpanElement>(
    'span[data-type="inlineMath"]:not([data-katex-rendered])',
  );
  for (const node of nodes) {
    const latex = node.getAttribute("data-latex") ?? "";
    const displayMode = node.getAttribute("data-display") === "yes";
    if (!latex) continue;
    try {
      katex.render(latex, node, {
        displayMode,
        throwOnError: false,
        // Don't let KaTeX expand ``\href`` / ``\url`` / etc. — Bible-school
        // teachers don't need them and they enlarge the attack surface.
        trust: false,
        // Suppress the red "ParseError" output element in favour of just
        // showing the broken latex literal — looks much less alarming
        // when a teacher fat-fingered a backslash.
        strict: "ignore",
      });
      node.setAttribute("data-katex-rendered", "true");
    } catch {
      // ``throwOnError: false`` already swallows render errors and
      // shows the source; this catch is the belt-and-braces guard
      // against an unexpected katex bug.
      continue;
    }
  }
}
