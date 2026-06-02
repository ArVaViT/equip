/**
 * Walks ``container`` for ``<pre>`` blocks (the rendered shape of
 * code blocks from ``CodeBlockLowlight``) and attaches a small
 * "Copy" button to each. The button copies the inner code text
 * (not the highlighted token DOM) to the clipboard and flashes a
 * brief "Copied" state on success.
 *
 * Why a DOM walk instead of a React component? The chapter HTML
 * is dropped via ``dangerouslySetInnerHTML``; there's no React
 * tree to inject into. We use the same view-time-rewrite pattern
 * the math + toggle-callout renderers use (see
 * ``lib/katex-render.ts`` and ``lib/callout-toggle.ts``).
 * Idempotent via the ``data-copy-attached`` flag.
 *
 * Localisation note: the helper accepts ``labels`` so callers can
 * pass i18n strings without forcing this lib to import i18next.
 */
export interface CopyLabels {
  copy: string
  copied: string
  ariaLabel: string
}

export function attachCopyButtonsIn(
  container: HTMLElement | null,
  labels: CopyLabels,
): void {
  if (!container) return
  const blocks = container.querySelectorAll<HTMLPreElement>(
    "pre:not([data-copy-attached])",
  )
  for (const pre of blocks) {
    pre.setAttribute("data-copy-attached", "true")
    // The button is absolutely positioned over the top-right corner
    // of the ``<pre>``; the parent gets ``relative`` so the button
    // anchors correctly.
    pre.style.position = pre.style.position || "relative"

    const button = document.createElement("button")
    button.type = "button"
    button.setAttribute("aria-label", labels.ariaLabel)
    button.textContent = labels.copy
    // Tailwind utility classes inlined here because the helper
    // doesn't go through the JSX path. The classes match the
    // ``.prose pre`` semantic-token palette so the button looks
    // native in both themes.
    button.className =
      "absolute right-2 top-2 z-10 rounded border border-edge bg-surface/90 px-2 py-1 text-xs font-medium text-ink-muted opacity-0 transition-opacity hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand group-hover:opacity-100 focus:opacity-100"

    // Make the button appear on hover by promoting the parent to a
    // tailwind ``group``. Idempotent: ``classList.add`` doesn't
    // duplicate.
    pre.classList.add("group")

    button.addEventListener("click", async () => {
      const codeEl = pre.querySelector("code")
      const text = (codeEl ?? pre).textContent ?? ""
      try {
        await navigator.clipboard.writeText(text)
        const original = button.textContent
        button.textContent = labels.copied
        // Restore the label after a short flash. Using a class
        // toggle would be cleaner but adds CSS surface for a
        // one-off ephemeral state.
        window.setTimeout(() => {
          button.textContent = original
        }, 1400)
      } catch {
        // Clipboard write can fail on insecure origins or when
        // permission is denied. Fail silently — the teacher / student
        // can still select + Cmd+C the text manually.
      }
    })

    pre.appendChild(button)
  }
}
