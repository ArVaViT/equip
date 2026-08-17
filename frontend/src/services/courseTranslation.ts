import api from "./api"
import type { SupportedLocale } from "@/i18n/config"

/**
 * How far a course is from existing in every language — and what a
 * teacher can do about it.
 *
 * Two calls, and they answer different questions:
 *
 * - `progress` is read-only and cheap. The editor polls it while a
 *   course is being prepared, and the publish button reads it to know
 *   whether the gate will let the course through. It is computed from
 *   the same completeness the gate itself uses, so the two cannot
 *   disagree.
 * - `prepare` is the "translate it now" action. The pipeline leaves
 *   drafts alone on purpose — translating text that is still being
 *   rewritten spends money on wording that will not survive — so
 *   without this, every field of a large course is translated at the
 *   moment of publication and the course sits invisible until that
 *   finishes.
 */

export interface TranslationGapSummary {
  /** No translation exists yet. The pipeline has not got here. */
  missing: number
  /** A translation came back and failed its structural check. Needs a person. */
  needs_review: number
  /** The provider call did not produce text. Retryable. */
  failed: number
}

export interface CourseTranslationProgress {
  course_id: string
  status: string
  required: number
  present: number
  is_complete: boolean
  /** Remaining (field, locale) pairs per language. */
  by_locale: Partial<Record<SupportedLocale, number>>
  gaps: TranslationGapSummary
  /** Edits to a live course held until every language has them. */
  held_edits: number
  /** Held edits that will not resolve without someone looking. */
  blocked_edits: number
  /** False when no translation provider is configured. */
  enabled: boolean
}

export interface PrepareResult {
  translated: number
  skipped: number
  failed: number
  enabled: boolean
  /** True when the work went to the worker; poll `progress` for the rest. */
  queued: boolean
}

export const courseTranslationService = {
  async progress(courseId: string): Promise<CourseTranslationProgress> {
    const { data } = await api.get<CourseTranslationProgress>(
      `/courses/${courseId}/translation-progress`,
    )
    return data
  },

  async prepare(courseId: string): Promise<PrepareResult> {
    const { data } = await api.post<PrepareResult>(`/courses/${courseId}/translate`)
    return data
  },
}
