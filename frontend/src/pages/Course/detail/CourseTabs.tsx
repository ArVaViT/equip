import { useId, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { ReadingMinutes } from "@/components/course/ReadingMinutes"
import { useAsyncData } from "@/hooks/useAsyncData"
import { CHAPTER_TYPE_META, normalizeChapterType } from "@/lib/chapterTypes"
import type { CourseStructure } from "@/lib/courseStructure"
import { toProxyImage } from "@/lib/images"
import { orNotTranslated } from "@/lib/untranslated"
import { coursesService } from "@/services/courses"

type Tab = "about" | "program" | "author"
const TABS: Tab[] = ["about", "program", "author"]
const LABEL_KEYS: Record<Tab, string> = {
  about: "courseDetail.tabs.about",
  program: "courseDetail.tabs.program",
  author: "courseDetail.tabs.author",
}

interface Props {
  courseId: string
  structure: CourseStructure
  /** What the course is: its description, its group's dates. */
  about: ReactNode
  /** False when there is nothing to say: the tab is left out rather than
   *  opened onto a blank. */
  hasAbout: boolean
}

/**
 * The course before enrolling, the way BibleProject's course pages show it:
 * what it is, what is in it, who teaches it. It used to be a title, a
 * description and a button — a visitor could not see a single lesson name
 * before signing up for all of them.
 *
 * WAI-ARIA tabs, as the profile's: arrow keys move, only the open panel is in
 * the tab order.
 */
export function CourseTabs({ courseId, structure, about, hasAbout }: Props) {
  const { t } = useTranslation()
  const tabs = hasAbout ? TABS : TABS.filter((tab) => tab !== "about")
  const [active, setActive] = useState<Tab>(tabs[0] ?? "program")
  const base = useId()

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const i = tabs.indexOf(active)
    const next =
      e.key === "ArrowRight" ? tabs[(i + 1) % tabs.length]
      : e.key === "ArrowLeft" ? tabs[(i - 1 + tabs.length) % tabs.length]
      : e.key === "Home" ? tabs[0]
      : e.key === "End" ? tabs[tabs.length - 1]
      : undefined
    if (!next) return
    e.preventDefault()
    setActive(next)
    document.getElementById(`${base}-tab-${next}`)?.focus()
  }

  return (
    <section className="mt-8">
      <div
        role="tablist"
        aria-label={t("courseDetail.tabs.label")}
        onKeyDown={onKeyDown}
        className="flex gap-1 border-b border-edge"
      >
        {tabs.map((tab) => (
          <button
            key={tab}
            id={`${base}-tab-${tab}`}
            type="button"
            role="tab"
            aria-selected={active === tab}
            aria-controls={`${base}-panel-${tab}`}
            tabIndex={active === tab ? 0 : -1}
            onClick={() => setActive(tab)}
            className={`-mb-px min-h-11 min-w-0 flex-auto border-b-2 px-2 py-2.5 text-center text-sm font-medium leading-tight transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand sm:flex-none sm:px-4 ${
              active === tab ? "border-brand text-ink" : "border-transparent text-ink-muted hover:text-ink"
            }`}
          >
            {t(LABEL_KEYS[tab])}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`${base}-panel-${active}`}
        aria-labelledby={`${base}-tab-${active}`}
        tabIndex={0}
        className="pt-5 focus-visible:outline-none"
      >
        {active === "about" && about}
        {active === "program" && <Program courseId={courseId} structure={structure} />}
        {active === "author" && <Author courseId={courseId} />}
      </div>
    </section>
  )
}

/** Every lesson by name, in order, with its kind and its minutes. Not links:
 *  they open once the reader is enrolled. */
function Program({ courseId, structure }: { courseId: string; structure: CourseStructure }) {
  const { t, i18n } = useTranslation()
  const { data: minutes } = useAsyncData(
    async () => {
      try {
        return (await coursesService.getReadingTime(courseId)).chapters
      } catch {
        return {}
      }
    },
    [courseId, i18n.language],
  )

  if (structure.chapters.length === 0) {
    return <p className="text-sm text-ink-muted">{t("courseDetail.tabs.programEmpty")}</p>
  }

  return (
    <ol className="space-y-6">
      {structure.groups.map((group, gi) => (
        <li key={group.module?.id ?? `loose-${gi}`}>
          {group.module && (
            <h3 className="mb-2 flex items-baseline gap-2 font-serif text-base font-semibold tracking-tight text-wrap-safe">
              <span className="tabular-nums text-ink-muted">{gi + 1}.</span>
              {orNotTranslated(t, group.module.title)}
            </h3>
          )}
          <ul className="divide-y divide-edge rounded-card border border-edge bg-card dark:border-transparent">
            {group.chapters.map((chapter) => {
              const Icon = CHAPTER_TYPE_META[normalizeChapterType(chapter.chapter_type)].icon
              const m = minutes?.[chapter.id] ?? 0
              return (
                <li key={chapter.id} className="flex items-center gap-3 px-4 py-3">
                  <Icon className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                  <span className="min-w-0 flex-1 text-sm text-ink text-wrap-safe">
                    {orNotTranslated(t, chapter.title)}
                  </span>
                  {m > 0 && <ReadingMinutes minutes={m} className="shrink-0 gap-1 text-xs text-ink-muted" />}
                </li>
              )
            })}
          </ul>
        </li>
      ))}
    </ol>
  )
}

function Author({ courseId }: { courseId: string }) {
  const { t } = useTranslation()
  const { data: author, loading } = useAsyncData(
    async () => {
      try {
        return await coursesService.getAuthor(courseId)
      } catch {
        return null
      }
    },
    [courseId],
  )
  if (loading) return null
  if (!author?.name) return <p className="text-sm text-ink-muted">{t("courseDetail.tabs.authorUnknown")}</p>

  const initial = author.name.trim().charAt(0).toLocaleUpperCase()
  return (
    <div className="flex items-center gap-4">
      {author.avatar_url ? (
        <img
          src={toProxyImage(author.avatar_url)}
          alt=""
          className="h-16 w-16 shrink-0 rounded-full object-cover"
          loading="lazy"
          decoding="async"
        />
      ) : (
        <div
          aria-hidden
          className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-muted font-serif text-2xl text-ink-muted"
        >
          {initial}
        </div>
      )}
      <div className="min-w-0">
        <p className="font-serif text-lg font-semibold tracking-tight text-wrap-safe">{author.name}</p>
        {author.school && <p className="text-sm text-ink-muted text-wrap-safe">{author.school}</p>}
      </div>
    </div>
  )
}
