import type { ReadinessCheck } from "@/services/courseReadiness"

/**
 * The narrowest slice of ``t`` this helper needs. ``useTranslation().t``
 * satisfies it; so does a stub in a test.
 */
type Translate = (key: string | string[], options?: Record<string, unknown>) => string

const PASSED_PREFIX = "courseReadiness.checks."
const MISSING_PREFIX = "courseReadiness.missing."

/**
 * The sentence for one readiness check, in the tense that matches its state.
 *
 * The backend hands every check a single ``message_key`` written in the
 * affirmative — "The course has a cover image." — because that is the row
 * a teacher sees crossed out once the check passes. Shown for a *failing*
 * check, and especially listed under "Publish with issues?", the same
 * sentence reads as "all good" when it means the opposite. So each
 * ``checks.*`` key has a ``missing.*`` twin ("The course has no cover
 * image.") that we prefer while the check is not passed, falling back to
 * the affirmative key for a check the frontend has not learned about yet.
 */
export function readinessMessage(t: Translate, check: ReadinessCheck): string {
  const options = { defaultValue: check.message_key, title: check.subject?.title }
  if (check.passed || !check.message_key.startsWith(PASSED_PREFIX)) {
    return t(check.message_key, options)
  }
  const missingKey = MISSING_PREFIX + check.message_key.slice(PASSED_PREFIX.length)
  return t([missingKey, check.message_key], options)
}
