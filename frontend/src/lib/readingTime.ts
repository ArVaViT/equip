/**
 * How long a lesson takes to read, in whole minutes.
 *
 * Microsoft Learn prints minutes beside every unit and Medium above every
 * article; an adult deciding "can I finish this at lunch" needs exactly
 * that number, and a lesson that says nothing reads as open-ended.
 *
 * Words per minute by language, on the slow side of adult reading because
 * this is study, not skimming: Russian and Ukrainian words are longer and
 * read more slowly than English ones.
 */
const WORDS_PER_MINUTE: Record<string, number> = { ru: 160, uk: 160, de: 180, en: 220 }

/** Words in a piece of lesson HTML: letters in a row, tags and entities dropped. */
export function wordsIn(html: string): number {
  const text = html.replace(/<[^>]+>/g, " ").replace(/&[a-z#0-9]+;/gi, " ")
  return text.match(/\p{L}[\p{L}\p{M}'’-]*/gu)?.length ?? 0
}

/** Minutes to read these HTML fragments in `lang`; 0 when under half a minute. */
export function readingMinutes(htmls: string[], lang: string): number {
  const words = htmls.reduce((n, html) => n + wordsIn(html), 0)
  const wpm = WORDS_PER_MINUTE[lang.slice(0, 2).toLowerCase()] ?? 200
  return Math.round(words / wpm)
}
