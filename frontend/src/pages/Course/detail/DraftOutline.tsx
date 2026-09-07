import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight, BookOpen } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CHAPTER_TYPE_LABEL_KEYS, CHAPTER_TYPE_META, normalizeChapterType } from "@/lib/chapterTypes"
import { chapterHref, type CourseStructure } from "@/lib/courseStructure"
import { orNotTranslated } from "@/lib/untranslated"
import type { Chapter } from "@/types"

interface Props {
  courseId: string
  structure: CourseStructure
}

/**
 * The course as its author will walk through it before anyone else can.
 *
 * The server hands a course's owner the modules and chapters of a draft
 * (``catalog.py`` lets the owner and an admin past the published check),
 * and the chapter routes let the owner in without an enrollment. The page
 * used to throw that away: the owner saw a cover, two counters and an
 * "Enroll" button that answered with "this course is not published yet".
 * A teacher who wanted to read their own lesson the way a student would
 * had no door.
 *
 * This is the door: every lesson of the course, each a link into the student
 * view. No progress, no locks — there is no enrollment for progress to belong
 * to, and a teacher checking their work should not have to pass their own quiz
 * to reach the next lesson.
 *
 * It walked `modules[].chapters`, so a lesson written straight into the course
 * was missing from the author's own preview — the one screen whose whole job
 * is «show me what I made». It reads the course's structure now, and a course
 * with no modules previews as its lessons.
 */
export function DraftOutline({ courseId, structure }: Props) {
  const { t } = useTranslation()

  return (
    <section aria-labelledby="draft-outline-heading" data-testid="draft-outline">
      <h2
        id="draft-outline-heading"
        className="mb-3 flex items-center gap-2 font-serif text-lg font-semibold tracking-tight"
      >
        <BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("courseDetail.preview.heading")}
        <span className="text-sm font-normal text-ink-muted">({structure.chapters.length})</span>
      </h2>

      {structure.groups.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("courseDetail.preview.empty")}</p>
      ) : (
        <div className="space-y-2">
          {structure.groups.map((group, idx) =>
            group.module ? (
              <Card key={group.module.id} className="transition-colors hover:border-brand/25">
                <CardHeader className="px-4 py-3">
                  <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-semibold text-brand-ink"
                      aria-hidden
                    >
                      {idx + 1}
                    </span>
                    <Link
                      to={`/courses/${courseId}/modules/${group.module.id}`}
                      className="min-w-0 flex-1 truncate hover:text-brand hover:underline underline-offset-2"
                    >
                      {orNotTranslated(t, group.module.title)}
                    </Link>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3 pt-0">
                  {group.chapters.length === 0 ? (
                    <p className="ml-8 text-xs text-ink-muted">
                      {t("courseDetail.preview.emptyModule")}
                    </p>
                  ) : (
                    <ChapterLinks courseId={courseId} chapters={group.chapters} inset />
                  )}
                </CardContent>
              </Card>
            ) : (
              // The lessons no module groups. No card and no heading over
              // them: a heading here would be a module by another name, and
              // the point is that these lessons need none.
              <Card key="ungrouped" className="transition-colors">
                <CardContent className="px-4 py-2">
                  <ChapterLinks courseId={courseId} chapters={group.chapters} />
                </CardContent>
              </Card>
            ),
          )}
        </div>
      )}
    </section>
  )
}

function ChapterLinks({
  courseId,
  chapters,
  inset = false,
}: {
  courseId: string
  chapters: Chapter[]
  inset?: boolean
}) {
  const { t } = useTranslation()
  return (
    <ul className={`divide-y divide-edge dark:divide-white/5 ${inset ? "ml-8" : ""}`}>
      {chapters.map((chapter) => {
        const kind = normalizeChapterType(chapter.chapter_type)
        const Icon = CHAPTER_TYPE_META[kind].icon
        return (
          <li key={chapter.id}>
            <Link
              to={chapterHref(courseId, chapter.id)}
              className="group flex items-center gap-2 py-2 text-sm text-ink transition-colors hover:text-brand"
            >
              <Icon
                className="h-3.5 w-3.5 shrink-0 text-ink-muted"
                strokeWidth={1.75}
                aria-hidden
              />
              <span className="min-w-0 flex-1 truncate">
                {orNotTranslated(t, chapter.title)}
              </span>
              <span className="shrink-0 text-xs text-ink-muted">
                {t(CHAPTER_TYPE_LABEL_KEYS[kind])}
              </span>
              <ArrowRight
                className="h-3.5 w-3.5 shrink-0 text-brand opacity-0 transition-opacity group-hover:opacity-100"
                strokeWidth={1.75}
                aria-hidden
              />
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
