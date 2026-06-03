import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate, useSearchParams } from "react-router-dom"
import { ArrowRight, Languages, RefreshCw, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, ErrorState, PageHeader } from "@/components/patterns"
import { Badge } from "@/components/ui/badge"
import {
  adminDailyChallengeService,
  type AdminDailyChallengeQueueItem,
  type DailyChallengeStatus,
} from "@/services/adminDailyChallenge"

const STATUS_OPTIONS: DailyChallengeStatus[] = [
  "doctrinally_reviewed",
  "bilingually_reviewed",
  "scripture_validated",
  "draft",
  "pilot_passed",
  "published",
]

/**
 * Editorial queue for the bilingual review surface. Lists questions
 * that need editor attention (default = doctrinally_reviewed — the
 * stage where the bilingual review actually happens), filterable by
 * status and by "needs RU". Clicking a row opens the side-by-side
 * detail editor.
 */
export default function DailyChallengeReviewPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const status = (searchParams.get("status") as DailyChallengeStatus | null) ?? "doctrinally_reviewed"
  const missingRu = searchParams.get("missing_ru") === "1"

  const [items, setItems] = useState<AdminDailyChallengeQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const res = await adminDailyChallengeService.listQueue({
        status,
        only_missing_ru: missingRu || undefined,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch {
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [status, missingRu])

  useEffect(() => {
    void load()
  }, [load])

  const setStatusFilter = (next: DailyChallengeStatus) => {
    const params = new URLSearchParams(searchParams)
    params.set("status", next)
    setSearchParams(params, { replace: false })
  }

  const setMissingRuFilter = (next: boolean) => {
    const params = new URLSearchParams(searchParams)
    if (next) params.set("missing_ru", "1")
    else params.delete("missing_ru")
    setSearchParams(params, { replace: false })
  }

  return (
    <div className="container mx-auto max-w-5xl px-4 py-6 sm:py-8">
      <PageHeader
        title={
          <h1 className="flex items-center gap-2 font-serif text-2xl font-bold tracking-tight sm:text-3xl">
            <Languages className="h-6 w-6 text-brand" strokeWidth={1.75} aria-hidden />
            {t("admin.dailyChallenge.review.title")}
          </h1>
        }
        description={
          <p className="text-sm text-ink-muted">
            {t("admin.dailyChallenge.review.description")}
          </p>
        }
        actions={
          <Button size="sm" variant="outline" onClick={() => void load()} disabled={loading}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t("admin.dailyChallenge.review.refresh")}
          </Button>
        }
      />

      <section className="mt-6 rounded-md bg-card">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-ink-muted">
              {t("admin.dailyChallenge.review.filterStatus")}
            </span>
            <select
              value={status}
              onChange={(e) => setStatusFilter(e.target.value as DailyChallengeStatus)}
              className="h-7 rounded-md bg-surface px-2 text-xs"
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {t(`admin.dailyChallenge.review.status.${s}`)}
                </option>
              ))}
            </select>
            <label className="ml-3 flex items-center gap-1.5 text-xs text-ink-muted">
              <input
                type="checkbox"
                checked={missingRu}
                onChange={(e) => setMissingRuFilter(e.target.checked)}
              />
              {t("admin.dailyChallenge.review.filterMissingRu")}
            </label>
          </div>
          {!loading && !loadError && (
            <span className="text-xs tabular-nums text-ink-muted">
              {t("admin.dailyChallenge.review.totalCount", { count: total })}
            </span>
          )}
        </header>

        <div className="divide-y divide-border">
          {loading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : loadError ? (
            <ErrorState
              className="py-6"
              title={t("admin.dailyChallenge.review.loadError")}
              action={
                <Button size="sm" variant="outline" onClick={load}>
                  {t("common.tryAgain")}
                </Button>
              }
            />
          ) : items.length === 0 ? (
            <EmptyState
              variant="compact"
              icon={<Sparkles strokeWidth={1.75} aria-hidden />}
              title={t("admin.dailyChallenge.review.empty.title")}
              description={t("admin.dailyChallenge.review.empty.body")}
            />
          ) : (
            items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => navigate(`/admin/daily-challenge/review/${item.id}`)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:bg-muted/40"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-serif text-sm font-semibold tracking-tight text-ink">
                    {item.bible_book} {item.bible_chapter}
                    {item.bible_verse_from != null
                      ? `:${item.bible_verse_from}${
                          item.bible_verse_to && item.bible_verse_to !== item.bible_verse_from
                            ? `-${item.bible_verse_to}`
                            : ""
                        }`
                      : ""}
                  </p>
                  <p className="mt-0.5 text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                    {t(`admin.dailyChallenge.review.status.${item.status}`)}
                  </p>
                </div>
                <CvBadges item={item} t={t} />
                <ArrowRight className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
              </button>
            ))
          )}
        </div>
      </section>
    </div>
  )
}

interface CvBadgesProps {
  item: AdminDailyChallengeQueueItem
  t: (key: string, opts?: Record<string, unknown>) => string
}

function CvBadges({ item, t }: CvBadgesProps) {
  return (
    <div className="hidden items-center gap-1.5 sm:flex">
      <Badge variant={item.has_en ? "primarySubtle" : "destructiveSubtle"}>
        {item.has_en ? "EN ✓" : t("admin.dailyChallenge.review.missingEn")}
      </Badge>
      <Badge variant={item.has_ru ? "primarySubtle" : "destructiveSubtle"}>
        {item.has_ru ? "RU ✓" : t("admin.dailyChallenge.review.missingRu")}
      </Badge>
    </div>
  )
}
