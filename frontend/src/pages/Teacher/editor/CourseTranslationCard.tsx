import { useTranslation } from "react-i18next"
import { AlertTriangle, CheckCircle2, Globe, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { LOCALE_NATIVE_LABELS, isSupportedLocale } from "@/i18n/config"
import { cn } from "@/lib/utils"
import type { CourseTranslationProgress } from "@/services/courseTranslation"

interface Props {
  progress: CourseTranslationProgress | null
  loading: boolean
  preparing: boolean
  onPrepare: () => void
}

/**
 * What this course looks like to the people who do not read its language.
 *
 * The editor already tells a teacher whether their course is structurally
 * ready. It said nothing about whether it exists in the other three
 * languages — which, on a platform whose promise is that a German writes
 * a course and Ukrainians take it, is the same question asked about the
 * audience rather than the author.
 *
 * Three things it has to make plain:
 *
 * 1. **Which audience is waiting.** One percentage would hide it. A
 *    course complete in three languages and empty in the fourth is not
 *    75% ready; it is not ready for Germans.
 * 2. **That preparing is a thing you can do now.** Drafts are not
 *    translated automatically, so without this button all of the work
 *    happens at publication and the course sits invisible while it runs.
 * 3. **When an edit is stuck.** A held edit whose translation failed its
 *    check does not resolve on its own. Left unsaid, the teacher reads
 *    it as a save that did nothing and retypes the same words.
 */
export function CourseTranslationCard({ progress, loading, preparing, onPrepare }: Props) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <section
        className="mb-6 overflow-hidden rounded-md border border-edge bg-card dark:border-transparent"
        aria-busy="true"
      >
        <div className="flex items-center gap-4 px-5 py-4">
          <Skeleton className="h-10 w-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-32" />
          </div>
          <Skeleton className="h-8 w-32 rounded-md" />
        </div>
      </section>
    )
  }

  // No provider configured — nothing will ever translate, and a panel
  // reporting "0 of 0" would only puzzle the reader.
  if (!progress || !progress.enabled) return null

  const remaining = Math.max(progress.required - progress.present, 0)
  const behind = Object.entries(progress.by_locale)
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1])
  const stuck = progress.blocked_edits > 0 || progress.gaps.needs_review > 0
  const done = progress.is_complete && progress.held_edits === 0

  return (
    <section className="mb-6 overflow-hidden rounded-md border border-edge bg-card dark:border-transparent">
      <div className="flex flex-wrap items-center gap-4 px-5 py-4">
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
            done
              ? "bg-success/10 text-success-ink"
              : stuck
                ? "bg-destructive/10 text-destructive-ink"
                : "bg-muted text-ink-muted",
          )}
          aria-hidden
        >
          {done ? (
            <CheckCircle2 className="h-5 w-5" strokeWidth={1.75} />
          ) : stuck ? (
            <AlertTriangle className="h-5 w-5" strokeWidth={1.75} />
          ) : (
            <Globe className="h-5 w-5" strokeWidth={1.75} />
          )}
        </span>

        <div className="min-w-[12rem] flex-1">
          <h2 className="font-serif text-base font-semibold text-ink">
            {t("courseTranslation.title")}
          </h2>
          <p className="mt-0.5 text-sm text-ink-muted">
            {done
              ? t("courseTranslation.complete")
              : t("courseTranslation.remaining", { count: remaining })}
          </p>
        </div>

        {!done && (
          <Button type="button" size="sm" onClick={onPrepare} disabled={preparing}>
            {preparing && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} />}
            {t("courseTranslation.prepare")}
          </Button>
        )}
      </div>

      {behind.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 border-t border-edge px-5 py-3 text-sm dark:border-white/5">
          {behind.map(([locale, count]) => (
            <li key={locale} className="text-ink-muted">
              <span className="text-ink">
                {isSupportedLocale(locale) ? LOCALE_NATIVE_LABELS[locale] : locale}
              </span>{" "}
              {t("courseTranslation.behindBy", { count })}
            </li>
          ))}
        </ul>
      )}

      {progress.held_edits > 0 && (
        <p className="border-t border-edge px-5 py-3 text-sm text-ink-muted dark:border-white/5">
          {t("courseTranslation.heldEdits", { count: progress.held_edits })}
        </p>
      )}

      {stuck && (
        <p className="border-t border-edge px-5 py-3 text-sm text-destructive dark:border-white/5">
          {progress.blocked_edits > 0
            ? t("courseTranslation.blockedEdits", { count: progress.blocked_edits })
            : t("courseTranslation.needsReview", { count: progress.gaps.needs_review })}
        </p>
      )}
    </section>
  )
}
