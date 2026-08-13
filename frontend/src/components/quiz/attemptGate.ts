import type { QuizAttempt } from "@/types"

/**
 * Whether a student may start this quiz, and what we are entitled to claim.
 *
 * `getMyQuizAttempts` answered `[]` on a failed request, so "we could not
 * find out how many attempts you have used" became "you have used none".
 * `attemptsReached` was then `false` and the quiz opened as if fresh. A
 * student out of attempts could sit through an entire exam and have the
 * submission refused at the end — after doing the work.
 *
 * The file next door already shows the product cares about exactly this:
 * submit is blocked below an essay's minimum length "so students don't
 * accidentally submit half-written work and burn an attempt on an exam".
 *
 * Unknown is a third answer, and here it resolves differently from the
 * chapter lock. Refusing to start would block somebody who *does* have
 * attempts left; opening silently risks wasted work. So it opens **and says
 * so** — the student decides with the truth in front of them, and the server
 * remains the only thing that actually counts.
 */
export type Attempts = QuizAttempt[] | null

export interface AttemptGate {
  /** `null` when unknown — render nothing rather than a confident "0 of 3". */
  used: number | null
  /** Only ever true on a count we actually have. */
  exhausted: boolean
  /** Warn before they spend an hour on something that may not submit. */
  countUnverified: boolean
}

export function attemptGate(attempts: Attempts, maxAttempts: number | null): AttemptGate {
  if (attempts === null) {
    return { used: null, exhausted: false, countUnverified: maxAttempts !== null }
  }
  const used = attempts.filter((a) => !!a.completed_at).length
  return {
    used,
    exhausted: maxAttempts !== null && used >= maxAttempts,
    countUnverified: false,
  }
}
