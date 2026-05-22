/**
 * Walks ``container`` for ``<div data-callout="toggle">`` elements (the
 * stored shape produced by the TipTap Callout extension's ``toggle``
 * variant) and replaces each with a native ``<details><summary>`` /
 * body pair so the student gets a real click-to-expand affordance.
 *
 * Why do this at view time instead of in the extension's ``renderHTML``?
 * Native ``<details>`` is a two-slot element (summary + body), but
 * TipTap's ``renderHTML`` only supports one content hole per node.
 * Rather than fight the schema, the editor stores the toggle as a
 * single-slot ``<div data-callout="toggle">``, and we rewrite to
 * ``<details>`` on read. Idempotent via the ``data-toggle-rendered``
 * flag.
 *
 * Sanitiser allowlist: ``details`` + ``summary`` are HTML5 standard
 * elements with no scripting potential; ``app/core/sanitize.py`` and
 * the frontend DOMPurify config both accept them.
 */
export function renderToggleCalloutsIn(container: HTMLElement | null): void {
  if (!container) return;
  const toggles = container.querySelectorAll<HTMLDivElement>(
    'div[data-callout="toggle"]:not([data-toggle-rendered])',
  );
  for (const el of toggles) {
    const children = Array.from(el.children);
    if (children.length === 0) {
      // Empty callout — flag as rendered so we don't re-scan.
      el.setAttribute("data-toggle-rendered", "true");
      continue;
    }
    const first = children[0];
    const rest = children.slice(1);
    if (!first) {
      // Defensive — ``children.length === 0`` already returned above,
      // but the type narrower wants it again to drop the ``undefined``.
      continue;
    }
    const details = document.createElement("details");
    // Preserve every attribute from the source div (class, data-*, etc.)
    // so the .callout-cascade CSS still targets it after the rewrite.
    for (const attr of Array.from(el.attributes)) {
      details.setAttribute(attr.name, attr.value);
    }
    details.setAttribute("data-toggle-rendered", "true");
    // ``<summary>`` can wrap inline content directly; moving the
    // first child's children keeps any inline formatting (bold, link,
    // scripture-ref, math marker) intact.
    const summary = document.createElement("summary");
    while (first.firstChild) summary.appendChild(first.firstChild);
    details.appendChild(summary);
    for (const child of rest) details.appendChild(child);
    el.replaceWith(details);
  }
}
