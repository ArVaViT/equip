/**
 * An ``http(s)://`` address inside plain text. Stops at whitespace and at
 * the quote marks a teacher writes around a link in any of the four
 * languages; trailing sentence punctuation is peeled off afterwards so
 * «см. https://zoom.us/j/1.» does not carry the full stop into the URL.
 */
const URL_RE = /https?:\/\/[^\s<>"'«»„“”‘’]+/g
const TRAILING_PUNCTUATION = /[.,;:!?)\]]+$/

export type TextSegment = { kind: "text"; value: string } | { kind: "link"; value: string }

function count(haystack: string, needle: string): number {
  let n = 0
  for (const ch of haystack) if (ch === needle) n += 1
  return n
}

/** Split ``text`` into plain runs and the links inside them. */
export function linkifySegments(text: string): TextSegment[] {
  const out: TextSegment[] = []
  let last = 0
  for (const match of text.matchAll(URL_RE)) {
    const start = match.index ?? 0
    const raw = match[0]
    const trailing = TRAILING_PUNCTUATION.exec(raw)?.[0] ?? ""
    let keep = raw.length - trailing.length
    // A closing bracket only belongs to the URL when the URL opened one:
    // «…/Деяния_(книга)» keeps its bracket, «(см. https://x.y/z)» does not.
    for (const ch of trailing) {
      if (ch === ")" && count(raw.slice(0, keep), "(") > count(raw.slice(0, keep), ")")) {
        keep += 1
      } else {
        break
      }
    }
    const url = raw.slice(0, keep)
    if (start > last) out.push({ kind: "text", value: text.slice(last, start) })
    out.push({ kind: "link", value: url })
    last = start + url.length
  }
  if (last < text.length) out.push({ kind: "text", value: text.slice(last) })
  return out
}
