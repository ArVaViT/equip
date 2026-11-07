import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, useSearchParams } from "react-router-dom"
import { CheckCircle2, ChevronRight, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState, ErrorState, PageHeader } from "@/components/patterns"
import { Section } from "@/components/layout/Section"
import { gradesService } from "@/services/grades"
import { getErrorDetail } from "@/lib/errorDetail"
import { formatRelative } from "@/i18n/format"
import type { WaitingWork } from "@/types"
import { MarkOneByOne } from "./grading/MarkOneByOne"

type Group = {
  key: string
  title: string
  courseTitle: string
  count: number
  oldest: string | null
  start: number
}

/** The run as lessons: consecutive pieces answering the same thing. The
 *  server already orders them so each question's answers sit together. */
function groupsOf(items: WaitingWork[]): Group[] {
  const groups: Group[] = []
  items.forEach((item, i) => {
    const key = `${item.kind}:${item.course_id}:${item.item_id}`
    const last = groups[groups.length - 1]
    if (last?.key === key) {
      last.count++
      return
    }
    groups.push({
      key,
      title: item.title,
      courseTitle: item.course_title,
      count: 1,
      oldest: item.submitted_at,
      start: i,
    })
  })
  return groups
}

/**
 * «На проверку»: everything waiting on this teacher, across every course.
 *
 * The same set the dashboard counts — built on the same queries server-side —
 * so the number that led here is the number of pieces in the run, and marking
 * them all is what brings it to zero.
 *
 * Grouped by what was asked, not by student: thirty answers to one prompt in a
 * row, the standard loaded once instead of thirty times.
 */
export default function GradingQueue() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const courseFilter = params.get("course")
  const running = params.has("run")
  const [all, setAll] = useState<WaitingWork[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [startAt, setStartAt] = useState(0)
  const [finished, setFinished] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setAll(await gradesService.getRun())
    } catch (err) {
      // Not `[]`: an empty run reads «Всё проверено», and a run that did not
      // load is not one the teacher has finished.
      setAll(null)
      setLoadError(getErrorDetail(err, t("grading.loadFailed")))
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const items = useMemo(
    () => (all && courseFilter ? all.filter((i) => i.course_id === courseFilter) : all),
    [all, courseFilter],
  )
  const groups = useMemo(() => groupsOf(items ?? []), [items])

  const start = (at: number) => {
    setStartAt(at)
    setFinished(null)
    const next = new URLSearchParams(params)
    next.set("run", "1")
    // PUSH, so the phone's back gesture returns to the list rather than
    // leaving the page.
    setParams(next)
  }

  const leaveRun = (marked: number | null) => {
    const next = new URLSearchParams(params)
    next.delete("run")
    setParams(next, { replace: true })
    setFinished(marked)
    setAll(null)
    void load()
  }

  if (loadError) {
    return (
      <Section width="reading">
        <ErrorState
          description={loadError}
          action={
            <Button size="sm" variant="outline" onClick={() => void load()}>
              {t("common.tryAgain")}
            </Button>
          }
        />
      </Section>
    )
  }

  if (items === null) {
    return (
      <Section width="reading">
        <div className="flex items-center gap-2 py-8 text-sm text-ink-muted">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          {t("common.loading")}
        </div>
      </Section>
    )
  }

  if (running && items.length > 0) {
    return (
      <Section width="reading">
        <MarkOneByOne
          items={items}
          startAt={startAt}
          onExit={() => leaveRun(null)}
          onFinish={(marked) => leaveRun(marked)}
        />
      </Section>
    )
  }

  const courseTitle = courseFilter ? items[0]?.course_title : null
  const othersWaiting = courseFilter && all ? all.length - items.length : 0

  if (items.length === 0) {
    // Calm, and not a dead end: where to go next is right under it.
    return (
      <Section width="reading">
        <EmptyState
          titleAs="h1"
          className="border-none bg-transparent py-16"
          icon={<CheckCircle2 strokeWidth={1.75} className="text-success-ink" />}
          title={t("grading.emptyTitle")}
          description={finished ? t("grading.markedNow", { count: finished }) : undefined}
          action={
            <div className="flex w-64 max-w-full flex-col gap-2">
              {othersWaiting > 0 && (
                <Button asChild className="h-12 text-base">
                  <Link to="/teacher/review">{t("grading.otherCourses", { count: othersWaiting })}</Link>
                </Button>
              )}
              <Button asChild variant={othersWaiting > 0 ? "outline" : "default"} className="h-12 text-base">
                <Link to="/teacher">{t("grading.toDashboard")}</Link>
              </Button>
            </div>
          }
        />
      </Section>
    )
  }

  return (
    <Section width="reading">
      <PageHeader
        title={t("grading.title")}
        description={`${courseTitle ? `${courseTitle} · ` : ""}${t("grading.waitingCount", { count: items.length })}`}
      />
      {finished != null && finished > 0 && (
        <p className="-mt-2 mb-4 text-sm text-success-ink">{t("grading.markedNow", { count: finished })}</p>
      )}

      <Button onClick={() => start(0)} className="mb-6 h-12 w-full text-base">
        {t("grading.start")}
        <ChevronRight className="ml-1 h-4 w-4" strokeWidth={1.75} aria-hidden />
      </Button>

      <ul className="space-y-2">
        {groups.map((group) => (
          <li key={group.key}>
            <button
              type="button"
              onClick={() => start(group.start)}
              className="flex min-h-16 w-full items-center gap-3 rounded-card border border-edge bg-surface p-4 text-left transition-colors hover:bg-heritage focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <span className="min-w-0 flex-1">
                <span className="line-clamp-2 break-words font-medium">{group.title}</span>
                <span className="mt-0.5 block truncate text-sm text-ink-muted">
                  {/* Age, not size. The essay waiting three weeks is the one
                      somebody is upset about. */}
                  {courseFilter ? "" : `${group.courseTitle} · `}
                  {formatRelative(group.oldest)}
                </span>
              </span>
              <span className="shrink-0 rounded-md bg-warning/15 px-2 py-0.5 text-sm font-medium tabular-nums text-warning-ink">
                {group.count}
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
            </button>
          </li>
        ))}
      </ul>

      {courseFilter && othersWaiting > 0 && (
        <Button asChild variant="ghost" className="mt-4 h-11 w-full">
          <Link to="/teacher/review">{t("grading.otherCourses", { count: othersWaiting })}</Link>
        </Button>
      )}
    </Section>
  )
}
