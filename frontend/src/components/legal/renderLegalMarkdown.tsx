import type { ReactNode } from "react"

/**
 * A small renderer for the exact Markdown subset the legal documents use.
 *
 * Not a Markdown library, and not `dangerouslySetInnerHTML` over one. Two
 * reasons, and the second is the real one:
 *
 * 1. A parser plus a sanitiser is a large dependency and a standing XSS
 *    surface for two static pages that are read a handful of times each.
 * 2. This produces React elements, so there is no HTML string anywhere in the
 *    path and therefore nothing to sanitise. The question does not arise.
 *
 * The subset is deliberately closed: headings, paragraphs, bullets, numbered
 * lists, tables, bold, links, horizontal rules. Anything else renders as plain
 * text rather than silently disappearing — a legal document that drops a
 * clause because the renderer did not recognise it is the worst failure this
 * file could have.
 */

/**
 * `**bold**` and `[text](/path)`, and nothing else.
 *
 * Links were missing until 2026-09-17, so every cross-reference between the
 * documents rendered as its own source: a reader following "see the
 * [Privacy Policy](/privacy)" was reading square brackets. The documents now
 * point at each other in earnest — the terms send teachers to the Teacher &
 * Contributor Agreement, the privacy policy sends everyone to the provider
 * list — and a legal cross-reference that is not a link is a cross-reference
 * most people will not follow.
 *
 * A plain anchor rather than a router `Link`: these render inside a page that
 * has a router, but the renderer itself is a pure function that other things
 * (and its own tests) call without one, and a full navigation to a document
 * page costs nothing anybody will notice.
 *
 * Only in-app paths. A link to `https://` from a document body would be a way
 * to point a reader off the platform from text that is supposed to be ours,
 * and nothing in these documents needs one.
 */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = []
  const pattern = /\*\*([^*]+)\*\*|\[([^\]]+)\]\((\/[^)\s]*)\)/g
  let last = 0
  let match: RegExpExecArray | null
  let i = 0
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index))
    if (match[1] !== undefined) {
      out.push(
        <strong key={`${keyPrefix}-b${i++}`} className="font-semibold text-ink">
          {match[1]}
        </strong>,
      )
    } else {
      out.push(
        <a
          key={`${keyPrefix}-a${i++}`}
          href={match[3]}
          className="text-brand underline underline-offset-4"
        >
          {match[2]}
        </a>,
      )
    }
    last = match.index + match[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function tableRow(line: string): string[] {
  return line
    .slice(line.startsWith("|") ? 1 : 0, line.endsWith("|") ? -1 : undefined)
    .split("|")
    .map((cell) => cell.trim())
}

const isTableLine = (line: string) => line.trimStart().startsWith("|")
const isDivider = (line: string) => /^\|[\s|:-]+\|$/.test(line.trim())

export function renderLegalMarkdown(source: string): ReactNode[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n")
  const blocks: ReactNode[] = []
  let paragraph: string[] = []
  let bullets: string[] = []
  let numbered: string[] = []

  const flushParagraph = () => {
    if (paragraph.length === 0) return
    const text = paragraph.join(" ")
    blocks.push(
      <p key={`p${blocks.length}`} className="mt-4 leading-[1.7] text-ink">
        {inline(text, `p${blocks.length}`)}
      </p>,
    )
    paragraph = []
  }

  const flushBullets = () => {
    if (bullets.length === 0) return
    blocks.push(
      <ul key={`ul${blocks.length}`} className="mt-4 space-y-2 pl-5">
        {bullets.map((item, i) => (
          <li key={i} className="list-disc leading-[1.7] text-ink marker:text-ink-muted">
            {inline(item, `ul${blocks.length}-${i}`)}
          </li>
        ))}
      </ul>,
    )
    bullets = []
  }

  const flushNumbered = () => {
    if (numbered.length === 0) return
    blocks.push(
      <ol key={`ol${blocks.length}`} className="mt-4 space-y-2 pl-5">
        {numbered.map((item, i) => (
          <li key={i} className="list-decimal leading-[1.7] text-ink marker:text-ink-muted">
            {inline(item, `ol${blocks.length}-${i}`)}
          </li>
        ))}
      </ol>,
    )
    numbered = []
  }

  const flush = () => {
    flushParagraph()
    flushBullets()
    flushNumbered()
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!
    const trimmed = line.trim()

    if (!trimmed) {
      flush()
      continue
    }

    if (trimmed.startsWith("# ")) {
      flush()
      blocks.push(
        <h1
          key={`h${blocks.length}`}
          /* A single long word — "Политика конфиденциальности",
             "Datenschutzerklärung" — is wider than a 390px phone at 3xl and
             pushed the whole document sideways. Smaller on phones, and
             breakable as a last resort so no translation can do it again. */
          className="font-serif text-2xl font-semibold tracking-tight text-ink break-words sm:text-3xl"
        >
          {trimmed.slice(2)}
        </h1>,
      )
      continue
    }

    if (trimmed.startsWith("## ")) {
      flush()
      blocks.push(
        <h2
          key={`h${blocks.length}`}
          /* ``break-words`` for the same reason the h1 has it, found the same
             way: "Urheberrechtsbeschwerden" is a single 24-character word and
             at 320px it pushed the German terms 13px wider than the viewport.
             German compounds this document cannot avoid — Haftungsbeschränkung,
             Datenschutzerklärung — are all in this range. */
          className="mt-10 break-words font-serif text-xl font-semibold tracking-tight text-ink"
        >
          {trimmed.slice(3)}
        </h2>,
      )
      continue
    }

    if (trimmed.startsWith("- ")) {
      flushParagraph()
      flushNumbered()
      bullets.push(trimmed.slice(2))
      continue
    }

    // `1.` through `9.` — the notice-and-counter-notice procedure in the terms
    // is a numbered list, and the numbers are load-bearing: a takedown notice
    // has to contain six specific things, and a reader has to be able to count
    // them.
    const ordered = /^(\d{1,2})\.\s+(.*)$/.exec(trimmed)
    if (ordered) {
      flushParagraph()
      flushBullets()
      numbered.push(ordered[2]!)
      continue
    }

    if (isTableLine(trimmed)) {
      flush()
      const rows: string[][] = []
      while (i < lines.length && isTableLine(lines[i]!.trim())) {
        const current = lines[i]!.trim()
        if (!isDivider(current)) rows.push(tableRow(current))
        i++
      }
      i-- // the loop's own increment will step past the line that ended the table
      const [head, ...body] = rows
      blocks.push(
        <div key={`t${blocks.length}`} className="mt-5 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {head?.map((cell, c) => (
                  <th
                    key={c}
                    className="border-b border-edge-strong pb-2 pr-4 text-left font-medium text-ink"
                  >
                    {inline(cell, `th${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c} className="border-b border-edge py-2 pr-4 align-top text-ink">
                      {inline(cell, `td${r}-${c}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    if (/^-{3,}$/.test(trimmed)) {
      flush()
      blocks.push(<hr key={`hr${blocks.length}`} className="mt-8 border-edge" />)
      continue
    }

    paragraph.push(trimmed)
  }

  flush()
  return blocks
}
