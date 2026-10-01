/**
 * Questions pasted as plain text — the way a volunteer brings a test, from Word.
 *
 * Fifty questions typed into the editor one field at a time is where a teacher
 * gives up. The format is the one Moodle calls Aiken, which people write
 * without knowing its name, made tolerant of how it arrives from a document:
 *
 *     Who wrote the Acts of the Apostles?
 *     A. Peter
 *     B. Luke
 *     C. Paul
 *     ANSWER: B
 *
 * - Questions are separated by a blank line.
 * - Options are a letter and `.` or `)`: Latin `A.`/`a)` or Cyrillic `А.`/`Б)`.
 * - The right one is named by an answer line (ANSWER / ОТВЕТ / ВІДПОВІДЬ /
 *   ANTWORT / ПРАВИЛЬНО), or marked with `*` before or after the option.
 * - A question may run over several lines before its options.
 *
 * Every block is either a question or a reason it is not one, so the preview
 * can say exactly which question to fix instead of dropping it silently.
 */

export interface ImportedQuestion {
  question_text: string
  options: { option_text: string; is_correct: boolean }[]
}

export type ImportProblem = "no_options" | "one_option" | "no_answer" | "answer_not_an_option" | "two_answers"

export interface ImportBlock {
  /** First line of the block, for the preview to point at. */
  start: string
  question?: ImportedQuestion
  problem?: ImportProblem
}

const OPTION = /^\s*\*?\s*([A-Za-zА-ЯЁа-яёІіЇїЄєҐґ])[.)]\s+(.*?)\s*$/u
// `(?!\p{L})`, not `\b`: in JavaScript `\b` knows only ASCII letters, even
// with the `u` flag, so "Ответ: Б" never ended in a word boundary.
const ANSWER = /^\s*(?:ANSWER|ОТВЕТ|ВІДПОВІДЬ|ANTWORT|ПРАВИЛЬНО|ПРАВИЛЬНЫЙ ОТВЕТ|ПРАВИЛЬНА ВІДПОВІДЬ)\s*[:\-–—]\s*([A-Za-zА-ЯЁа-яёІіЇїЄєҐґ])(?!\p{L})/iu

/** Latin and Cyrillic letters that look alike name the same option: А and A, В and B. */
function letterKey(letter: string): string {
  const upper = letter.toUpperCase()
  const twins: Record<string, string> = { А: "A", В: "B", С: "C", Е: "E", К: "K", М: "M", Н: "H", О: "O", Р: "P", Т: "T", Х: "X" }
  // Cyrillic lists usually go А Б В Г Д: map by position too, below.
  return twins[upper] ?? upper
}

const CYRILLIC_ORDER = "АБВГДЕЖЗИКЛМН"
const LATIN_ORDER = "ABCDEFGHIJKLM"

/** The letters of a block, in order, so "Б" can be found whether the options were written А Б В or A B C. */
function positionOf(letter: string, letters: string[]): number {
  const upper = letter.toUpperCase()
  const direct = letters.findIndex((l) => l.toUpperCase() === upper)
  if (direct >= 0) return direct
  const twin = letters.findIndex((l) => letterKey(l) === letterKey(upper))
  if (twin >= 0) return twin
  const cyr = CYRILLIC_ORDER.indexOf(upper)
  if (cyr >= 0 && cyr < letters.length) return cyr
  const lat = LATIN_ORDER.indexOf(upper)
  if (lat >= 0 && lat < letters.length) return lat
  return -1
}

export function parseQuestionsText(text: string): ImportBlock[] {
  const blocks = text
    .replace(/\r\n?/g, "\n")
    .split(/\n\s*\n/)
    .map((b) => b.split("\n").map((l) => l.replace(/\u00a0/g, " ")).filter((l) => l.trim() !== ""))
    .filter((lines) => lines.length > 0)

  return blocks.map((lines) => {
    const start = lines[0]!.trim()
    const stem: string[] = []
    const letters: string[] = []
    const options: { option_text: string; starred: boolean }[] = []
    let answerLetter: string | null = null

    for (const line of lines) {
      const answer = line.match(ANSWER)
      if (answer) {
        answerLetter = answer[1]!
        continue
      }
      const option = options.length > 0 || stem.length > 0 ? line.match(OPTION) : null
      if (option) {
        const raw = option[2]!
        const starred = /^\s*\*/.test(line) || /\*\s*$/.test(raw)
        letters.push(option[1]!)
        options.push({ option_text: raw.replace(/\s*\*\s*$/, "").trim(), starred })
      } else if (options.length === 0) {
        stem.push(line.trim())
      } else {
        // A line after the options that is neither an option nor the answer
        // continues the last option (a long option wrapped in the document).
        options[options.length - 1]!.option_text += ` ${line.trim()}`
      }
    }

    if (options.length === 0) return { start, problem: "no_options" as const }
    if (options.length === 1) return { start, problem: "one_option" as const }
    const starred = options.flatMap((o, i) => (o.starred ? [i] : []))
    let correct: number
    if (answerLetter !== null) {
      correct = positionOf(answerLetter, letters)
      if (correct < 0) return { start, problem: "answer_not_an_option" as const }
    } else if (starred.length === 1) {
      correct = starred[0]!
    } else if (starred.length > 1) {
      return { start, problem: "two_answers" as const }
    } else {
      return { start, problem: "no_answer" as const }
    }
    return {
      start,
      question: {
        question_text: stem.join("\n"),
        options: options.map((o, i) => ({ option_text: o.option_text, is_correct: i === correct })),
      },
    }
  })
}
