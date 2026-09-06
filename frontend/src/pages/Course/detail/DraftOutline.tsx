import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight, BookOpen } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CHAPTER_TYPE_LABEL_KEYS, CHAPTER_TYPE_META, normalizeChapterType } from "@/lib/chapterTypes"
import { orNotTranslated } from "@/lib/untranslated"
import type { Module } from "@/types"

interface Props {
  courseId: string
  modules: Module[]
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
 * This is the door: every module, every chapter, each a link into the
 * student view. No progress, no locks — there is no enrollment for
 * progress to belong to, and a teacher checking their work should not
 * have to pass their own quiz to reach the next module.
 */
export function DraftOutline({ courseId, modules }: Props) {
  const { t } = useTranslation()
  const sorted = [...modules].sort((a, b) => a.order_index - b.order_index)

  return (
    <section aria-labelledby="draft-outline-heading" data-testid="draft-outline">
      <h2
        id="draft-outline-heading"
        className="mb-3 flex items-center gap-2 font-serif text-lg font-semibold tracking-tight"
      >
        <BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("courseDetail.preview.heading")}
        <span className="text-sm font-normal text-ink-muted">({sorted.length})</span>
      </h2>

      {sorted.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("courseDetail.preview.noModules")}</p>
      ) : (
        <div className="space-y-2">
          {sorted.map((module, idx) => {
            const chapters = [...(module.chapters ?? [])].sort(
              (a, b) => a.order_index - b.order_index,
            )
            return (
              <Card key={module.id} className="transition-colors hover:border-brand/25">
                <CardHeader className="px-4 py-3">
                  <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-semibold text-brand-ink"
                      aria-hidden
                    >
                      {idx + 1}
                    </span>
                    <Link
                      to={`/courses/${courseId}/modules/${module.id}`}
                      className="min-w-0 flex-1 truncate hover:text-brand hover:underline underline-offset-2"
                    >
                      {orNotTranslated(t, module.title)}
                    </Link>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3 pt-0">
                  {chapters.length === 0 ? (
                    <p className="ml-8 text-xs text-ink-muted">
                      {t("courseDetail.preview.emptyModule")}
                    </p>
                  ) : (
                    <ul className="ml-8 divide-y divide-edge dark:divide-white/5">
                      {chapters.map((chapter) => {
                        const kind = normalizeChapterType(chapter.chapter_type)
                        const Icon = CHAPTER_TYPE_META[kind].icon
                        return (
                          <li key={chapter.id}>
                            <Link
                              to={`/courses/${courseId}/modules/${module.id}/chapters/${chapter.id}`}
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
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </section>
  )
}
