/**
 * Turns the references a lesson block cites into buttons that open the verse.
 *
 * The server decides what is a reference (it has the parser and the book
 * names in four languages); this only finds those exact strings in the
 * rendered block and wraps them. A reference split across elements — the
 * book in bold, the numbers not — is left as text: wrapping it would mean
 * restructuring the author's markup, and a missed link costs less than that.
 *
 * Text inside links, buttons, code and rendered math is never touched.
 */

/**
 * The block's text as the server should read it: one line per text node.
 * `textContent` runs the end of one paragraph or list item into the start of
 * the next, and «Рим 8:28» + «1 Кор. 13:4» read as «Рим 8:281 Кор. 13:4» —
 * a verse that does not exist, so neither reference opened.
 */
export function textForScripture(root: HTMLElement): string {
  const parts: string[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  for (let n = walker.nextNode(); n; n = walker.nextNode()) parts.push(n.nodeValue ?? "")
  return parts.join("\n")
}

const SKIP = "a, button, code, pre, .katex, kbd, summary, [data-type=\"inlineMath\"]"

function escape(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * Wrap every occurrence of each `written` string under `root`. Returns how
 * many were wrapped. The button carries the index into `written` in
 * `data-verse`; whitespace in a reference matches any space, because the
 * typography pass ties «Ин 3:16» with a no-break space.
 */
export function linkScriptureIn(root: HTMLElement | null, written: string[], label: (written: string) => string): number {
  if (!root) return 0
  // Undo an earlier pass first: its buttons index an older list, and a
  // button kept from it would open somebody else's verse.
  const earlier = root.querySelectorAll("button.verse-ref")
  if (earlier.length > 0) {
    earlier.forEach((b) => b.replaceWith(b.textContent ?? ""))
    root.normalize()
  }
  if (written.length === 0) return 0
  const alternatives = written
    .map((w, i) => [w, i] as const)
    // Longest first, so «1 Кор. 13:4» is not taken as a shorter reference inside it.
    .sort((a, b) => b[0].length - a[0].length)
    .map(([w, i]) => `(?<v${i}>${escape(w).replace(/\s+/g, "[\\s\\u00a0]+")})`)
    .join("|")
  // Not inside a longer word or number: «Деян. 1:8» is not in «Деян. 1:80».
  const pattern = new RegExp(`(?<![\\p{L}\\d])(?:${alternatives})(?!\\d)`, "gu")
  const texts: Text[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) =>
      node.parentElement?.closest(SKIP) || node.parentElement?.closest("[data-verse]")
        ? NodeFilter.FILTER_REJECT
        : NodeFilter.FILTER_ACCEPT,
  })
  for (let n = walker.nextNode(); n; n = walker.nextNode()) texts.push(n as Text)

  let wrapped = 0
  for (const node of texts) {
    const value = node.nodeValue ?? ""
    pattern.lastIndex = 0
    const matches = [...value.matchAll(pattern)]
    if (matches.length === 0) continue
    const fragment = document.createDocumentFragment()
    let at = 0
    for (const m of matches) {
      const index = Object.entries(m.groups ?? {}).find(([, v]) => v !== undefined)?.[0]
      if (index === undefined || m.index === undefined) continue
      fragment.append(value.slice(at, m.index))
      const button = document.createElement("button")
      button.type = "button"
      button.className = "verse-ref"
      button.dataset.verse = index.slice(1)
      button.setAttribute("aria-haspopup", "dialog")
      button.setAttribute("aria-label", label(m[0]))
      button.textContent = m[0]
      fragment.append(button)
      at = m.index + m[0].length
      wrapped += 1
    }
    fragment.append(value.slice(at))
    node.replaceWith(fragment)
  }
  return wrapped
}
