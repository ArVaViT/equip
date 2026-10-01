import type { ChapterInfo, StudentProgressData } from "./types"

/**
 * Who a Monday-morning note goes to, from the gradebook's own data.
 *
 * - `not_submitted` — nothing handed in for this piece of work, and not
 *   excused from it.
 * - `not_passed` — a test taken and failed (not one still waiting for its
 *   open answers to be read), or work returned for another try.
 * - `everyone` — the whole class.
 */
export type Audience = "not_submitted" | "not_passed" | "everyone"

const WORK_TYPES = new Set(["quiz", "exam", "assignment"])

export function isWork(chapter: Pick<ChapterInfo, "chapter_type">): boolean {
  return WORK_TYPES.has(chapter.chapter_type)
}

function standing(chapter: ChapterInfo | undefined, audience: Audience): boolean {
  if (audience === "everyone") return true
  if (!chapter || chapter.completed_by === "excused") return false
  if (audience === "not_submitted") return chapter.quiz_result === null && chapter.assignment_result === null
  const quiz = chapter.quiz_result
  if (quiz) return !quiz.passed && !quiz.awaiting_grading
  return chapter.assignment_result?.status === "returned"
}

export function pickRecipients(
  students: StudentProgressData[],
  chapterId: string | null,
  audience: Audience,
): StudentProgressData[] {
  return students.filter(
    (s) =>
      s.email &&
      (audience === "everyone" || standing(s.chapters.find((c) => c.id === chapterId), audience)),
  )
}

/**
 * A `mailto:` that opens the teacher's own mail with the class in Bcc —
 * nobody sees anybody else's address — and the subject filled in. Equip
 * sends nothing: the note is the teacher's, from the teacher.
 */
export function mailtoFor(emails: string[], subject: string): string {
  // `@` stays as it is (RFC 6068 allows it, and some clients mishandle %40).
  const bcc = emails.map((e) => encodeURIComponent(e).replace(/%40/g, "@")).join(",")
  return `mailto:?bcc=${bcc}&subject=${encodeURIComponent(subject)}`
}
