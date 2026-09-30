/**
 * Line-breaking a lesson the way a typesetter would.
 *
 * A browser breaks a line at any space, so «Ин» and «3:16» end up on two
 * lines, a lone «в» hangs at the end of one, and a dash starts the next.
 * These are the most common defects in Bible-study text and the cheapest
 * to prevent: a no-break space (U+00A0) where the break must not fall.
 *
 * Applied when the lesson is shown, not when it is saved: the stored text
 * stays what the teacher typed, and the editor never sees these spaces.
 */

const NBSP = " "

/** One-letter words that must not be left at the end of a line. */
const SHORT_WORDS: Record<string, RegExp> = {
  // в к с у о и а я — and their capitals.
  ru: /(^|[\s(«„"'—-])([вксуоиаяВКСУОИАЯ]) (?=\S)/gu,
  // в у з й і а о — Ukrainian has «і» and «й» where Russian has «и».
  uk: /(^|[\s(«„"'—-])([вузйіаоВУЗЙІАО]) (?=\S)/gu,
}

/** «Ин 3:16», «John 3:16», «Joh 3,16», «Пс. 22:1» — a book and its chapter stay together. */
const VERSE_REFERENCE = /(\p{L}{1,}\.?) (\d{1,3}[:,.]\d{1,3})/gu

/** «1 Кор», «2 Tim» — a numbered book keeps its number. */
const NUMBERED_BOOK = /(^|[\s(])([1-3]) (?=\p{Lu})/gu

/** Tie one run of text for `lang` (a BCP-47 tag or a bare code). */
export function tieText(text: string, lang: string): string {
  const code = lang.slice(0, 2).toLowerCase()
  let out = text.replace(VERSE_REFERENCE, `$1${NBSP}$2`).replace(NUMBERED_BOOK, `$1$2${NBSP}`)
  const short = SHORT_WORDS[code]
  if (short) {
    // Twice: «и в Иерусалиме» has two in a row, and a global replace does
    // not revisit the space the first match consumed.
    out = out.replace(short, `$1$2${NBSP}`).replace(short, `$1$2${NBSP}`)
    // A dash never starts a line in Russian or Ukrainian typesetting.
    out = out.replace(/ —/g, `${NBSP}—`)
  }
  return out
}

/** Elements whose text is not prose: code keeps its spaces, math its markers. */
const SKIP = "code, pre, kbd, samp, script, style, textarea, .katex, [data-no-typography]"

/**
 * Tie every prose text node under `root`. Text that still carries math
 * markers (`$`, `\(`) is left alone, so it runs safely before or after the
 * KaTeX pass.
 */
export function tieTypographyIn(root: HTMLElement | null, lang: string): void {
  if (!root) return
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text)
  for (const node of nodes) {
    const value = node.nodeValue
    if (!value || !value.includes(" ")) continue
    if (node.parentElement?.closest(SKIP)) continue
    if (value.includes("$") || value.includes("\\(") || value.includes("\\[")) continue
    const tied = tieText(value, lang)
    if (tied !== value) node.nodeValue = tied
  }
}
