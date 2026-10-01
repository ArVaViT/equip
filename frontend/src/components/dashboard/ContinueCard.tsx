import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
import { chapterHref } from "@/lib/courseStructure"
import { getRecentCourses } from "@/lib/recentlyViewed"
import { orNotTranslated } from "@/lib/untranslated"
import { coursesService } from "@/services/courses"
import { enrollmentsService } from "@/services/enrollments"
import { progressService } from "@/services/progress"

import { courseToContinue, nextLesson } from "./continueWhere"

/**
 * One button back to where the reader stopped: the next lesson not yet done
 * in the course they opened last. Duolingo's home is one "continue", edX has
 * "Resume course"; Equip's home was a shelf of equal cards and the reader
 * had to remember the rest (2026-09-30 platform study, practice 4).
 *
 * Renders nothing until it knows, and nothing for somebody with no course
 * in progress — the courses list below covers that case.
 */
export function ContinueCard() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const { data } = useAsyncData(
    async () => {
      if (!user) return null
      const enrollments = await enrollmentsService.getMyCourses().catch(() => [])
      const pick = courseToContinue(enrollments, getRecentCourses().map((r) => r.id))
      if (!pick) return null
      const [course, done] = await Promise.all([
        coursesService.getCourse(pick.course_id),
        progressService.getMyChapterProgress(pick.course_id).catch(() => null),
      ])
      // Unknown progress is not "nothing done": pointing at lesson 1 would
      // send somebody back to the start (see pages/Course/moduleProgress).
      if (done === null) return null
      const next = nextLesson(course, done)
      return next ? { course, ...next } : null
    },
    [user?.id, i18n.language],
  )

  if (!data) return null
  const { course, chapter, position, total } = data
  return (
    <section
      aria-labelledby="continue-heading"
      className="animate-fade-in flex flex-wrap items-center justify-between gap-3 rounded-card border border-edge bg-card p-4 shadow-card dark:border-transparent"
    >
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
          {t("dashboard.continue.eyebrow")} · {t("dashboard.continue.position", { current: position, total })}
        </p>
        <h2 id="continue-heading" className="mt-1 truncate font-serif text-lg font-semibold text-ink">
          {orNotTranslated(t, chapter.title)}
        </h2>
        <p className="truncate text-sm text-ink-muted">{orNotTranslated(t, course.title)}</p>
      </div>
      <Button asChild size="sm">
        <Link to={chapterHref(course.id, chapter.id)}>
          {t("dashboard.continue.cta")}
          <ArrowRight className="ml-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
        </Link>
      </Button>
    </section>
  )
}
