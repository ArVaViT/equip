import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useSearchParams } from "react-router-dom"
import { Check, ChevronLeft, ChevronRight, Languages, RefreshCw, Sparkles } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, ErrorState } from "@/components/patterns"
import { getErrorDetail } from "@/lib/errorDetail"
import {
  LOCALE_NATIVE_LABELS,
  SUPPORTED_LOCALES,
  isSupportedLocale,
  type SupportedLocale,
} from "@/i18n/config"
import { adminTranslationsService, type NeedsReviewRow } from "@/services/adminTranslations"

const PAGE_SIZE = 25

/**
 * The translations parked for a person, and the two things a person can
 * do about them.
 *
 * A machine translation that fails its structural check is kept and not
 * served. Readers filter on `ok`, so the row shows as "not translated
 * yet" — which means the course does not go out and edits to it are held
 * behind a row nobody can see. Retrying is no help on its own: at
 * temperature 0 the same source returns the same text and the same
 * verdict. It needs someone to read it.
 *
 * The endpoints for that have existed for a while. What did not exist
 * was anywhere to read the text, which is why nothing was ever accepted:
 * the ids they take could only be found by querying production by hand.
 *
 * So the row shows the source and the translation side by side, and the
 * reason the check gave, and where it came from — and then the two
 * buttons mean something:
 *
 * - **Accept** — "I read this; the check was wrong about it." The
 *   translation becomes servable and the reason stays on the row.
 * - **Retry** — "This really is wrong." The row goes back to the
 *   pipeline, which is worth doing once the prompt or the validator has
 *   changed, and pointless otherwise.
 */
export function TranslationReviewTab() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()

  // Filters live in the URL so the count on a course's translation card
  // can link straight to that course's rows, and so a reviewer working
  // through German can reload without losing their place.
  const localeParam = searchParams.get("locale")
  const locale = isSupportedLocale(localeParam) ? localeParam : null
  const courseId = searchParams.get("course")
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1)

  const [rows, setRows] = useState<NeedsReviewRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [actingId, setActingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const res = await adminTranslationsService.listNeedsReview({
        locale: locale ?? undefined,
        course_id: courseId ?? undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      })
      setRows(res.items)
      setTotal(res.total)
    } catch {
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [locale, courseId, page])

  useEffect(() => {
    void load()
  }, [load])

  const updateParams = (mutate: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(searchParams)
    mutate(params)
    setSearchParams(params)
  }

  const setLocaleFilter = (next: string) => {
    updateParams((params) => {
      if (isSupportedLocale(next)) params.set("locale", next)
      else params.delete("locale")
      // A filter change with a page number attached lands on a page that
      // may not exist in the narrower result, and reads as "empty".
      params.delete("page")
    })
  }

  const clearCourseFilter = () => {
    updateParams((params) => {
      params.delete("course")
      params.delete("page")
    })
  }

  const goToPage = (next: number) => {
    updateParams((params) => {
      if (next <= 1) params.delete("page")
      else params.set("page", String(next))
    })
  }

  const act = async (row: NeedsReviewRow, action: "accept" | "retry") => {
    setActingId(row.id)
    try {
      if (action === "accept") {
        await adminTranslationsService.accept([row.id])
        toast.success(t("admin.translationReview.toast.accepted"))
      } else {
        await adminTranslationsService.retry([row.id])
        toast.success(t("admin.translationReview.toast.retried"))
      }
      // Reload rather than dropping the row locally: either action moves
      // it out of `needs_review`, and the total in the header has to
      // follow it or the page starts lying about how much is left.
      await load()
    } catch (err) {
      // Two literal keys rather than one built from ``action``: the
      // static key-coverage guard only sees keys it can read at scan
      // time, and a key it cannot see is a key that can go missing.
      const fallback =
        action === "accept"
          ? t("admin.translationReview.toast.acceptError")
          : t("admin.translationReview.toast.retryError")
      toast.error(getErrorDetail(err) || fallback)
    } finally {
      setActingId(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <section className="rounded-md border border-edge bg-card dark:border-transparent">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex flex-wrap items-center gap-2">
          <Languages className="h-4 w-4 text-ink-muted" strokeWidth={1.75} aria-hidden />
          <h2 className="font-serif text-base font-semibold text-ink">
            {t("admin.translationReview.title")}
          </h2>
          <label className="ml-3 flex items-center gap-1.5 text-xs text-ink-muted">
            {t("admin.translationReview.filterLocale")}
            <select
              value={locale ?? ""}
              onChange={(e) => setLocaleFilter(e.target.value)}
              className="h-7 rounded-md bg-surface px-2 text-xs"
            >
              <option value="">{t("admin.translationReview.filterLocaleAny")}</option>
              {SUPPORTED_LOCALES.map((code: SupportedLocale) => (
                <option key={code} value={code}>
                  {LOCALE_NATIVE_LABELS[code]}
                </option>
              ))}
            </select>
          </label>
          {courseId && (
            <Button size="sm" variant="outline" onClick={clearCourseFilter}>
              {t("admin.translationReview.clearCourseFilter")}
            </Button>
          )}
        </div>
        <div className="flex items-center gap-3">
          {!loading && !loadError && (
            <span className="text-xs tabular-nums text-ink-muted">
              {t("admin.translationReview.totalCount", { count: total })}
            </span>
          )}
          <Button size="sm" variant="outline" onClick={() => void load()} disabled={loading}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t("admin.translationReview.refresh")}
          </Button>
        </div>
      </header>

      <p className="border-b border-edge px-4 py-3 text-sm text-ink-muted sm:px-5">
        {t("admin.translationReview.description")}
      </p>

      <div className="divide-y divide-border">
        {loading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : loadError ? (
          <ErrorState
            className="py-6"
            title={t("admin.translationReview.loadError")}
            action={
              <Button size="sm" variant="outline" onClick={() => void load()}>
                {t("common.tryAgain")}
              </Button>
            }
          />
        ) : rows.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Sparkles strokeWidth={1.75} aria-hidden />}
            title={t("admin.translationReview.empty.title")}
            description={t("admin.translationReview.empty.body")}
          />
        ) : (
          rows.map((row) => (
            <ReviewRow key={row.id} row={row} busy={actingId === row.id} onAct={act} />
          ))
        )}
      </div>

      {!loading && !loadError && total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-3 border-t border-edge px-4 py-3 sm:px-5">
          <p className="text-xs text-ink-muted">
            {t("admin.translationReview.page", { page, total: totalPages })}
          </p>
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => goToPage(page - 1)}
              className="h-9 w-9 p-0"
              aria-label={t("admin.translationReview.prevPageAria")}
            >
              <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => goToPage(page + 1)}
              className="h-9 w-9 p-0"
              aria-label={t("admin.translationReview.nextPageAria")}
            >
              <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}

interface ReviewRowProps {
  row: NeedsReviewRow
  busy: boolean
  onAct: (row: NeedsReviewRow, action: "accept" | "retry") => void
}

function ReviewRow({ row, busy, onAct }: ReviewRowProps) {
  const { t } = useTranslation()
  const sourceLabel =
    row.source_locale && isSupportedLocale(row.source_locale)
      ? LOCALE_NATIVE_LABELS[row.source_locale]
      : (row.source_locale ?? "")
  const targetLabel = isSupportedLocale(row.locale) ? LOCALE_NATIVE_LABELS[row.locale] : row.locale

  return (
    <article className="px-4 py-4 sm:px-5">
      <div className="flex flex-wrap items-center gap-2">
        {/* Where the row came from. An entity id alone tells a reviewer
            nothing about what they are reading. */}
        <span className="truncate font-serif text-sm font-semibold tracking-tight text-ink">
          {row.is_daily_challenge
            ? t("admin.translationReview.dailyChallenge")
            : (row.course_title ?? t("admin.translationReview.unknownCourse"))}
        </span>
        <Badge variant="infoSubtle">{targetLabel}</Badge>
        <span className="text-xs uppercase tracking-[0.14em] text-ink-muted">
          {row.entity_type} · {row.field}
        </span>
      </div>

      {row.review_reason && (
        <p className="mt-1.5 text-xs text-destructive">{row.review_reason}</p>
      )}

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-ink-muted">
            {t("admin.translationReview.sourceLabel", { language: sourceLabel })}
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink-muted">
            {row.source_text ?? t("admin.translationReview.sourceGone")}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-ink-muted">
            {t("admin.translationReview.translationLabel", { language: targetLabel })}
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink">{row.text}</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={busy} onClick={() => onAct(row, "accept")}>
          <Check className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {t("admin.translationReview.accept")}
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => onAct(row, "retry")}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {t("admin.translationReview.retry")}
        </Button>
      </div>
    </article>
  )
}
