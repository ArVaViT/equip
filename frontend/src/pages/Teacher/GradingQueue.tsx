import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, useSearchParams } from "react-router-dom"
import { ArrowLeft, ClipboardCheck, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState } from "@/components/patterns"
import { gradesService } from "@/services/grades"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import { relativeTime } from "@/pages/Teacher/progress/helpers"
import type { WaitingGroup } from "@/types"
import { MarkOneByOne } from "./grading/MarkOneByOne"

/**
 * Where a teacher marks.
 *
 * Until now the grading interface lived inside the course editor — dashboard,
 * course, editor, module, chapter, quiz editor, submissions tab. Grading is the
 * thing a teacher does weekly for years; authoring is what they do once, and
 * the weekly task sat seven levels inside the occasional one. The count shipped
 * in #961 had nowhere good to lead.
 *
 * Grouped by item, not by student: thirty answers to one prompt in a row, the
 * standard loaded once instead of thirty times. Marking a whole paper at a time
 * lets the standard drift between question one and question four, which is the
 * drift a rubric exists to prevent and a queue can prevent for free.
 */
export default function GradingQueue() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const openItem = params.get("assignment")
  const [groups, setGroups] = useState<WaitingGroup[] | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setGroups(await gradesService.getQueue())
    } catch (err) {
      toast({ title: getErrorDetail(err, t("grading.loadFailed")), variant: "destructive" })
      setGroups([])
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const open = (group: WaitingGroup) => {
    const next = new URLSearchParams(params)
    next.set("assignment", group.item_id)
    // PUSH, so the back button returns to the list rather than leaving the
    // page — a teacher works down the queue and back out of it constantly.
    setParams(next)
  }

  const closeItem = () => {
    const next = new URLSearchParams(params)
    next.delete("assignment")
    setParams(next)
    void load()
  }

  if (openItem) {
    const group = groups?.find((g) => g.item_id === openItem)
    return (
      <div className="container mx-auto max-w-3xl px-4 py-6">
        <Button variant="ghost" size="sm" onClick={closeItem} className="mb-3 -ml-2">
          <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("grading.backToQueue")}
        </Button>
        <MarkOneByOne assignmentId={openItem} title={group?.title} onDone={closeItem} />
      </div>
    )
  }

  return (
    <div className="container mx-auto max-w-3xl px-4 py-6 sm:py-8">
      <h1 className="mb-1 font-serif text-2xl font-bold tracking-tight sm:text-3xl">
        {t("grading.title")}
      </h1>
      <p className="mb-6 text-sm text-ink-muted">{t("grading.subtitle")}</p>

      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-ink-muted">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          {t("common.loading")}
        </div>
      ) : groups && groups.length === 0 ? (
        // An empty queue is worth saying out loud. A teacher who cleared it
        // should be told so, not shown a blank page that reads as a failure.
        <EmptyState
          icon={<ClipboardCheck strokeWidth={1.75} />}
          title={t("grading.emptyTitle")}
          description={t("grading.emptyBody")}
        />
      ) : (
        <div className="space-y-2">
          {groups?.map((group) => (
            <Card key={`${group.kind}:${group.item_id}`}>
              <CardContent className="flex items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="truncate font-medium">{group.title}</p>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    {/* Age, not size. The essay waiting three weeks is the one
                        somebody is upset about. */}
                    {t("grading.waitingSince", { when: relativeTime(group.oldest, t) })}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="rounded-md bg-warning/15 px-2 py-0.5 text-sm font-medium tabular-nums text-warning-ink">
                    {group.waiting}
                  </span>
                  {group.kind === "assignment" ? (
                    <Button size="sm" onClick={() => open(group)}>
                      {t("grading.mark")}
                    </Button>
                  ) : (
                    // Quiz answers are still marked on the quiz screen. Listing
                    // them here with a link is honest; pretending they open in
                    // the same flow would be a button that goes somewhere else.
                    <Link to={`/teacher/courses/${group.course_id}`}>
                      <Button size="sm" variant="outline">
                        {t("grading.openCourse")}
                      </Button>
                    </Link>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
