import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"
import { ArrowRight, BookOpen, Check, Loader2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { coursesService } from "@/services/courses"
import { enrollmentsService } from "@/services/enrollments"
import { toProxyImage } from "@/lib/images"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"
import type { Course } from "@/types"

interface Props {
  /** Fires after a successful enrollment of one or more picks. The
   *  orchestrator marks the flow complete; this component handles
   *  navigation to the first picked course's detail page. */
  onEnrolled: () => void
  /** Fires when the user explicitly chooses to browse instead — the
   *  orchestrator closes the flow and the user lands on the catalog
   *  with no enrollments. */
  onBrowse: () => void
  /** Fires when the user dismisses the picker without enrolling
   *  ("Maybe later") OR when the catalog is empty so there's nothing
   *  to pick. Same end state as ``onBrowse`` minus the catalog
   *  navigation. */
  onSkip: () => void
}

/**
 * First-run Step 3 — pick a starting course.
 *
 * Replaces the previous "auto-fire 13-step popover tour" with a
 * concrete first action: the user picks one or more courses from
 * the real catalog and lands on the first picked course's detail
 * page. Empty/error/zero-eligible states all degrade to the same
 * gracious skip → dashboard path.
 *
 * Why this shape over the popover tour: the popover tour explained
 * an empty UI (no courses, no progress, no certificates) by
 * pointing at empty rectangles. The user came to learn — getting
 * them in front of real content in under 60 seconds is the actual
 * onboarding job. Per-page tours still fire on the destination
 * surfaces (course detail / chapter view) so the contextual
 * orientation arrives at the moment it matters.
 */
export function CoursePickerStep({ onEnrolled, onBrowse, onSkip }: Props) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set())
  const [enrolling, setEnrolling] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  // Auto-skip when the catalog has nothing public + published to
  // offer. Surfacing an empty grid in the picker would be a worse
  // experience than just dropping to the dashboard.
  const autoSkip = useCallback(() => {
    onSkip()
  }, [onSkip])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    coursesService
      .getCourses()
      .then((data) => {
        if (cancelled) return
        const eligible = data.filter(
          (c) => c.access_mode === "public" && c.status === "published",
        )
        setCourses(eligible)
        setLoading(false)
        if (eligible.length === 0) autoSkip()
      })
      .catch(() => {
        if (cancelled) return
        setLoading(false)
        setError(true)
      })
    return () => {
      cancelled = true
    }
    // ``i18n.language`` rerolls localised course titles when the user
    // flipped language on the previous Setup step.
  }, [reloadKey, i18n.language, autoSkip])

  const toggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleEnroll = async () => {
    if (selectedIds.size === 0) return
    setEnrolling(true)
    const ids = Array.from(selectedIds)
    const results = await Promise.allSettled(
      ids.map((id) => enrollmentsService.enrollInCourse(id)),
    )
    setEnrolling(false)
    // Find the first ID that actually succeeded — preserves user's
    // pick order so the destination matches their first selection,
    // not whichever request the server happened to answer first.
    const firstSuccessId = ids.find((_id, i) => results[i]?.status === "fulfilled")
    const anyFailed = results.some((r) => r.status === "rejected")
    if (!firstSuccessId) {
      toast({ title: t("firstRun.picker.enrollAllFailed"), variant: "destructive" })
      return
    }
    if (anyFailed) {
      toast({ title: t("firstRun.picker.enrollSomeFailed"), variant: "destructive" })
    }
    onEnrolled()
    navigate(`/courses/${firstSuccessId}`)
  }

  const handleBrowse = () => {
    onBrowse()
    navigate("/courses")
  }

  return (
    <div className="flex w-full max-w-3xl flex-col items-center gap-5 text-center">
      <span className="block h-px w-12 bg-accent/60" aria-hidden />
      <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-accent">
        {t("firstRun.picker.eyebrow")}
      </p>
      <h1 className="font-serif text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-3xl">
        {t("firstRun.picker.title")}
      </h1>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
        {t("firstRun.picker.intro")}
      </p>

      <div className="mt-2 w-full">
        {loading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-36 rounded-md" />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border bg-muted/20 p-6 text-center">
            <p className="text-sm text-muted-foreground">
              {t("firstRun.picker.loadFailed")}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setReloadKey((k) => k + 1)}
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} />
              {t("common.tryAgain")}
            </Button>
          </div>
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {courses.map((course) => {
              const selected = selectedIds.has(course.id)
              const moduleCount = course.modules?.length ?? 0
              const cover = course.image_url ? toProxyImage(course.image_url) : null
              return (
                <li key={course.id}>
                  <button
                    type="button"
                    onClick={() => toggle(course.id)}
                    aria-pressed={selected}
                    disabled={enrolling}
                    className={cn(
                      "group relative flex h-full w-full items-start gap-3 rounded-md border-2 p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                      selected
                        ? "border-primary bg-primary/[0.06]"
                        : "border-transparent bg-muted/30 hover:border-primary/30 hover:bg-muted/50",
                      enrolling && "opacity-60",
                    )}
                  >
                    {cover ? (
                      <img
                        src={cover}
                        alt=""
                        loading="lazy"
                        className="h-16 w-16 shrink-0 rounded-sm border border-border object-cover"
                      />
                    ) : (
                      <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-sm border border-border bg-muted text-muted-foreground">
                        <BookOpen className="h-5 w-5" strokeWidth={1.75} aria-hidden />
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <h2 className="line-clamp-2 font-serif text-base font-semibold leading-tight tracking-tight text-foreground">
                        {course.title}
                      </h2>
                      {course.description && (
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                          {course.description}
                        </p>
                      )}
                      <p className="mt-2 text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground/80">
                        {t("firstRun.picker.modulesCount", { count: moduleCount })}
                      </p>
                    </div>
                    {selected && (
                      <span className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
                        <Check className="h-3 w-3" strokeWidth={3} aria-hidden />
                      </span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {!loading && !error && courses.length > 0 && (
        <div className="mt-2 flex w-full flex-col items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={selectedIds.size === 0 || enrolling}
            onClick={handleEnroll}
            className="w-full sm:w-auto sm:min-w-[220px]"
          >
            {enrolling ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} />
            ) : (
              <ArrowRight className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            )}
            {selectedIds.size <= 1
              ? t("firstRun.picker.enrollOne")
              : t("firstRun.picker.enrollMany", { count: selectedIds.size })}
          </Button>
          <div className="flex flex-col items-center gap-1 sm:flex-row sm:gap-3">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleBrowse}
              disabled={enrolling}
              className="text-muted-foreground hover:text-foreground"
            >
              {t("firstRun.picker.browseAll")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onSkip}
              disabled={enrolling}
              className="text-muted-foreground hover:text-foreground"
            >
              {t("firstRun.picker.skip")}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
