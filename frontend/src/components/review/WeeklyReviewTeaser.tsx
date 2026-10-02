import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ArrowRight, RotateCcw } from "lucide-react"

import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
import { orNotTranslated } from "@/lib/untranslated"
import { reviewService } from "@/services/review"

/**
 * "This week's review is ready" on the home page: one line per course that
 * has one, opening the course page at the review. Nothing when there is
 * nothing to review, or when the request fails — it is an invitation, not a
 * task list.
 */
export function WeeklyReviewTeaser() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const { data } = useAsyncData(
    async () => (user ? reviewService.waiting().catch(() => []) : []),
    [user?.id, i18n.language],
  )
  const list = data ?? []
  if (list.length === 0) return null
  return (
    <section
      aria-labelledby="weekly-review-teaser"
      className="overflow-hidden rounded-card border border-edge bg-card shadow-card dark:border-transparent"
    >
      {/* The same header as the other cards on the home page. */}
      <header className="flex items-center gap-2.5 border-b border-edge bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <RotateCcw className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
        <h2 id="weekly-review-teaser" className="truncate font-serif text-sm font-semibold tracking-tight text-ink">
          {t("review.teaser.title")}
        </h2>
      </header>
      <ul className="divide-y divide-edge">
        {list.map((r) => (
          <li key={r.course_id}>
            <Link
              to={`/courses/${r.course_id}#weekly-review`}
              className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-muted/40 sm:px-5"
            >
              <span className="min-w-0 truncate">
                {orNotTranslated(t, r.course_title ?? "")}
                <span className="text-ink-muted"> · {t("review.teaser.count", { count: r.count })}</span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
