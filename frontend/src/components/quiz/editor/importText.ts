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
 * - Questions are separated by a blank line — or not at all, the way Word
 *   pastes paragraphs: an answer line ends a question, and an option lettered
 *   A after options have begun starts the next one.
 * - Options are a letter and `.` or `)`: Latin `A.`/`a)` or Cyrillic `А.`/`Б)`,
 *   with or without a space after it.
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

const OPTION = /^\s*\*?\s*([A-Za-zА-ЯЁа-яёІіЇїЄєҐґ])[.)]\s*(\S.*?)\s*$/u
// `(?!\p{L})`, not `\b`: in JavaScript `\b` knows only ASCII letters, even
// with the `u` flag, so "Ответ: Б" never ended in a word boundary.
const ANSWER = /^\s*(?:ANSWER|ОТВЕТ|ВІДПОВІДЬ|ANTWORT|ПРАВИЛЬНО|ПРАВИЛЬНЫЙ ОТВЕТ|ПРАВИЛЬНА ВІДПОВІДЬ)\s*[:\-–—]\s*([A-Za-zА-ЯЁа-яёІіЇїЄєҐґ])(?!\p{L})(.*)$/iu
/** "ANSWER: B, C" — a second letter after the first: two answers, not one. */
const ANOTHER_LETTER = /^\s*(?:[,;/&+]|и|і|and|und)\s*[A-Za-zА-ЯЁа-яёІіЇїЄєҐґ](?!\p{L})/iu
const FIRST_LETTERS = new Set(["A", "А"])
const CYRILLIC = /[А-ЯЁа-яёІіЇїЄєҐґ]/u

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
  // By position only across alphabets — «Ответ: Б» for options A B C. In the
  // same alphabet a missing letter is a missing option, not the next one.
  const answerCyrillic = CYRILLIC.test(upper)
  if (letters.length === 0 || CYRILLIC.test(letters[0]!) === answerCyrillic) return -1
  const order = answerCyrillic ? CYRILLIC_ORDER : LATIN_ORDER
  const at = order.indexOf(upper)
  return at >= 0 && at < letters.length ? at : -1
}

interface Draft {
  lines: string[]
  stem: string[]
  letters: string[]
  options: { option_text: string; starred: boolean }[]
  /** Lines after the last option that are neither an option nor an answer. */
  trailing: string[]
  answer: string | null
  twoAnswers: boolean
}

const fresh = (stem: string[] = []): Draft => ({
  lines: [...stem],
  stem,
  letters: [],
  options: [],
  trailing: [],
  answer: null,
  twoAnswers: false,
})

function settle(d: Draft): ImportBlock | null {
  // Lines after the last option continue it: a long option wrapped in the document.
  if (d.trailing.length > 0 && d.options.length > 0) {
    d.options[d.options.length - 1]!.option_text += ` ${d.trailing.join(" ")}`
  } else {
    d.stem.push(...d.trailing)
  }
  if (d.lines.length === 0) return null
  const start = d.lines[0]!
  if (d.options.length === 0) return { start, problem: "no_options" }
  if (d.options.length === 1) return { start, problem: "one_option" }
  const starred = d.options.flatMap((o, i) => (o.starred ? [i] : []))
  if (d.twoAnswers) return { start, problem: "two_answers" }
  let correct: number
  if (d.answer !== null) {
    correct = positionOf(d.answer, d.letters)
    if (correct < 0) return { start, problem: "answer_not_an_option" }
    // A star and an answer line that disagree: which one the author meant is a guess.
    if (starred.length > 0 && !(starred.length === 1 && starred[0] === correct)) return { start, problem: "two_answers" }
  } else if (starred.length === 1) {
    correct = starred[0]!
  } else if (starred.length > 1) {
    return { start, problem: "two_answers" }
  } else {
    return { start, problem: "no_answer" }
  }
  return {
    start,
    question: {
      question_text: d.stem.join("\n"),
      options: d.options.map((o, i) => ({ option_text: o.option_text, is_correct: i === correct })),
    },
  }
}

export function parseQuestionsText(text: string): ImportBlock[] {
  const out: ImportBlock[] = []
  let d = fresh()
  const close = (next: Draft = fresh()) => {
    const block = settle(d)
    if (block) out.push(block)
    d = next
  }

  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.replace(/\u00a0/g, " ").trim()
    if (line === "") {
      if (d.lines.length > 0) close()
      continue
    }
    const answer = line.match(ANSWER)
    if (answer && d.options.length > 0) {
      d.lines.push(line)
      d.answer = answer[1]!
      d.twoAnswers = ANOTHER_LETTER.test(answer[2] ?? "")
      // The answer line ends the question, blank line or not.
      close()
      continue
    }
    const option = d.lines.length > 0 ? line.match(OPTION) : null
    if (option) {
      const letter = option[1]!
      if (d.options.length > 0 && FIRST_LETTERS.has(letter.toUpperCase())) {
        // Options lettered from A again: a new question began, and the lines
        // since the last option were its text.
        const stem = d.trailing
        d.trailing = []
        close(fresh(stem))
        if (stem.length === 0) {
          // An A with no question before it: keep it as text, so the preview
          // names the block instead of inventing a question.
          d.lines.push(line)
          d.stem.push(line)
          continue
        }
      }
      d.stem.push(...(d.options.length === 0 ? d.trailing : []))
      if (d.options.length > 0 && d.trailing.length > 0) {
        d.options[d.options.length - 1]!.option_text += ` ${d.trailing.join(" ")}`
      }
      d.trailing = []
      const body = option[2]!
      const starred = /^\*/.test(line) || /\*\s*$/.test(body)
      d.lines.push(line)
      d.letters.push(letter)
      d.options.push({ option_text: body.replace(/\s*\*\s*$/, "").trim(), starred })
      continue
    }
    d.lines.push(line)
    if (d.options.length === 0) d.stem.push(line)
    else d.trailing.push(line)
  }
  close()
  return out
}
