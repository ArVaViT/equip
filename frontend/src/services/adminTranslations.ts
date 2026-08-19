import api from "./api"
import type { SupportedLocale } from "@/i18n/config"

/**
 * The translations a machine produced and a check refused to serve.
 *
 * When a translation comes back and fails its structural check — a lost
 * scripture marker, halved markup, the wrong language — the row is kept
 * at `needs_review` and not served. Nothing about that state resolves on
 * its own: the model runs at temperature 0, so asking again returns the
 * same text and the same verdict. It waits for a person, and until one
 * acts the course stays out of the catalogue and edits to it stay
 * unpublished.
 *
 * Two endpoints have always been able to end that wait — accept the row
 * as servable, or re-open it for the pipeline. Neither had a queue to
 * read from: the ids they take could only come from a hand-written query
 * against production, so in practice nobody ran them. `listNeedsReview`
 * is that queue.
 */

export interface NeedsReviewRow {
  id: string
  entity_type: string
  entity_id: string
  field: string
  locale: string
  source_locale: string | null
  /** Why the check refused it, in words a person can act on. */
  review_reason: string | null
  /** What the provider returned. Stored so it can be read, not served. */
  text: string
  /** The text it was translated from. Null when the source is gone. */
  source_text: string | null
  created_at: string
  /** Null for content that belongs to no course — see `is_daily_challenge`. */
  course_id: string | null
  course_title: string | null
  /** Platform-wide content: the Daily Challenge rotation has no course. */
  is_daily_challenge: boolean
}

export interface NeedsReviewPage {
  items: NeedsReviewRow[]
  /** Everything matching the filters, not just this page. */
  total: number
  limit: number
  offset: number
}

export interface NeedsReviewParams {
  locale?: SupportedLocale
  course_id?: string
  limit?: number
  offset?: number
}

export interface ReviewActionResult {
  reset: number
}

export const adminTranslationsService = {
  async listNeedsReview(params: NeedsReviewParams = {}): Promise<NeedsReviewPage> {
    const { data } = await api.get<NeedsReviewPage>("/admin/translations/needs-review", { params })
    return data
  },

  /** A person read these and the check was wrong about them. */
  async accept(ids: string[]): Promise<ReviewActionResult> {
    const { data } = await api.post<ReviewActionResult>("/admin/translations/accept-reviewed", {
      ids,
    })
    return data
  },

  /** Hand these back to the pipeline — worth asking again, not worth serving. */
  async retry(ids: string[]): Promise<ReviewActionResult> {
    const { data } = await api.post<ReviewActionResult>("/admin/translations/retry-reviewed", {
      ids,
    })
    return data
  },
}
