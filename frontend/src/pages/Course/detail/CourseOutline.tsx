import { memo } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle,
  ChevronRight,
  Clock,
  Lock,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { EmptyState } from "@/components/patterns"
import { StaggerChildren } from "@/components/motion"
import ChapterTypeBadge from "@/components/course/ChapterTypeBadge"
import { isGradableChapterType } from "@/lib/chapterTypes"
import { chapterHref, type CourseOutlineGroup, type CourseStructure } from "@/lib/courseStructure"
import type { Chapter, Module } from "@/types"
import { formatDate } from "./types"
import { isChapterComplete, isChapterLocked, isChapterRead, isModuleLocked } from "../moduleProgress"
import { orNotTranslated } from "@/lib/untranslated"

/**
 * The course as a student walks it.
 *
 * This was `ModuleList`, and the name was the whole problem: it could only
 * draw modules, so a course whose lessons sit in no module rendered
 * «Модули (0)» over «преподаватель не опубликовал модулей» — a page telling
 * a student their four lessons do not exist. A module is a grouping now, and
 * a grouping a course may simply not use.
 *
 * So the outline draws `CourseStructure.groups`: a module keeps its card, and
 * the lessons no module holds are rows of their own at the tail. A course of
 * four lessons is four rows and the word «module» appears nowhere on it.
 *
 * ## What locks
 *
 * «Not until you have finished the one before» used to be two unrelated
 * rules: a whole module locked behind the previous module (here), and a
 * chapter locked behind the previous chapter *of its module* (`ModuleView`,
 * `ChapterView`). A lesson in no module fell through both — there was no
 * previous module, and no module to be previous within.
 *
 * The rule is one rule now, and it is the reading order: a lesson is locked
 * while the lesson before it **in the course** is an unfinished assessment.
 * A module row still locks behind the module before it, which is what makes
 * a course with sections look exactly as it did — and cannot contradict the
 * flat rule, because a module row is only unlocked once every assessment
 * before it is done, which is strictly more than the flat rule asks.
 */

interface Props {
  courseId: string
  structure: CourseStructure
  /** `null` when the progress request failed. See `moduleProgress.ts`. */
  completedChapterIds: Set<string> | null
}

function gradableIds(chapters: Chapter[]): string[] {
  return chapters.filter((ch) => isGradableChapterType(ch.chapter_type)).map((ch) => ch.id)
}

/** A row of the outline, resolved: which lock applies and where it sits. */
type OutlineRow =
  | { kind: "module"; key: string; group: CourseOutlineGroup; module: Module; ordinal: number; locked: boolean }
  | { kind: "lesson"; key: string; chapter: Chapter; position: number; locked: boolean }

/**
 * Flatten the outline into the rows the page draws, with each row's lock
 * already decided.
 *
 * Done in one pass rather than inside the rows, because both facts a row
 * needs — "am I locked" and "am I the first locked one" — are facts about
 * the list, not about the row. The hint sentence is stated once, next to
 * the first door it applies to; six modules behind five walls repeating one
 * sentence five times reads as nagging rather than explaining.
 */
function buildRows(structure: CourseStructure, completed: Set<string> | null): OutlineRow[] {
  const rows: OutlineRow[] = []
  let ordinal = 0
  // Position in the flat reading order, so a lesson row's number is the
  // lesson's number in the course — the same one `ChapterView` shows as
  // «Глава N из M».
  let position = 0

  structure.groups.forEach((group, groupIdx) => {
    if (group.module) {
      ordinal += 1
      const previous = structure.groups[groupIdx - 1]
      const locked =
        previous?.module != null &&
        isModuleLocked(completed, gradableIds(previous.chapters))
      rows.push({
        kind: "module",
        key: group.module.id,
        group,
        module: group.module,
        ordinal,
        locked,
      })
      position += group.chapters.length
      return
    }

    for (const chapter of group.chapters) {
      const previous = structure.chapters[position - 1] ?? null
      rows.push({
        kind: "lesson",
        key: chapter.id,
        chapter,
        position: position + 1,
        locked: isChapterLocked(
          completed,
          chapter,
          previous,
          previous ? isGradableChapterType(previous.chapter_type) : false,
        ),
      })
      position += 1
    }
  })

  return rows
}

export function CourseOutline({ courseId, structure, completedChapterIds }: Props) {
  const { t } = useTranslation()
  const rows = buildRows(structure, completedChapterIds)
  const firstLockedKey = rows.find((row) => row.locked)?.key ?? null

  const moduleCount = structure.groups.filter((g) => g.module !== null).length
  const hasLooseLessons = structure.groups.some((g) => g.module === null)
  // Three headings, because there are three courses. A course of modules is
  // still «Модули (3)» — nothing about it changed. A course of lessons is
  // «Уроки (4)». A course of both is its contents, counted in lessons,
  // because that is the only unit both halves share.
  const heading =
    moduleCount === 0
      ? { label: t("courseDetail.lessonsHeading"), count: structure.chapters.length }
      : hasLooseLessons
        ? { label: t("courseDetail.contentsHeading"), count: structure.chapters.length }
        : { label: t("courseDetail.modulesHeading"), count: moduleCount }

  return (
    <div>
      <h2 className="mb-3 flex items-center gap-2 font-serif text-lg font-semibold tracking-tight">
        <BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        {heading.label}
        <span className="text-sm font-normal text-ink-muted">({heading.count})</span>
      </h2>

      {rows.length > 0 ? (
        <StaggerChildren className="space-y-2">
          {rows.map((row) =>
            row.kind === "module" ? (
              <ModuleRow
                key={row.key}
                courseId={courseId}
                module={row.module}
                chapters={row.group.chapters}
                ordinal={row.ordinal}
                isLocked={row.locked}
                isFirstLocked={row.key === firstLockedKey}
                completedChapterIds={completedChapterIds}
              />
            ) : (
              <LessonRow
                key={row.key}
                courseId={courseId}
                chapter={row.chapter}
                position={row.position}
                isLocked={row.locked}
                isFirstLocked={row.key === firstLockedKey}
                completedChapterIds={completedChapterIds}
              />
            ),
          )}
        </StaggerChildren>
      ) : (
        <EmptyState
          icon={<BookOpen strokeWidth={1.75} aria-hidden />}
          title={t("courseDetail.noLessonsYet")}
          description={t("courseDetail.noLessonsYetDescription")}
        />
      )}
    </div>
  )
}

/** The circle at the head of a row: where the student stands on it. */
function RowMarker({
  locked,
  complete,
  read,
  ordinal,
  readLabel,
}: {
  locked: boolean
  complete: boolean
  read?: boolean
  ordinal: number
  readLabel?: string
}) {
  return (
    <span
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
        locked
          ? "bg-muted text-ink-muted"
          : complete
            ? "bg-success/15 text-success-ink"
            : "bg-brand/10 text-brand-ink"
      }`}
    >
      {locked ? (
        <Lock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
      ) : complete ? (
        <CheckCircle className="h-3 w-3" strokeWidth={1.75} aria-hidden />
      ) : read ? (
        // Quieter than the assessment tick, and a different glyph: a lesson
        // you have read is not an assessment you have passed.
        <Check className="h-3 w-3" strokeWidth={1.75} aria-label={readLabel} />
      ) : (
        ordinal
      )}
    </span>
  )
}

interface ModuleRowProps {
  courseId: string
  module: Module
  chapters: Chapter[]
  ordinal: number
  isLocked: boolean
  /** The first locked row is the only one that explains the rule. */
  isFirstLocked: boolean
  /** `null` when the progress request failed. See `moduleProgress.ts`. */
  completedChapterIds: Set<string> | null
}

const ModuleRow = memo(function ModuleRow({
  courseId,
  module,
  chapters,
  ordinal,
  isLocked,
  isFirstLocked,
  completedChapterIds,
}: ModuleRowProps) {
  const { t } = useTranslation()
  const gradable = chapters.filter((ch) => isGradableChapterType(ch.chapter_type))
  const gradableCount = gradable.length

  const allComplete =
    completedChapterIds !== null &&
    gradableCount > 0 &&
    gradable.every((ch) => completedChapterIds.has(ch.id))
  const completedInModule =
    completedChapterIds === null
      ? 0
      : gradable.filter((ch) => completedChapterIds.has(ch.id)).length

  return (
    <Card className={`group transition-colors ${isLocked ? "opacity-60" : "hover:border-brand/25"}`}>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <RowMarker locked={isLocked} complete={allComplete} ordinal={ordinal} />
            <span className="min-w-0 flex-1 truncate">{orNotTranslated(t, module.title)}</span>
            <span className="shrink-0 whitespace-nowrap text-xs font-normal text-ink-muted">
              {gradableCount > 0
                ? `${completedInModule}/${gradableCount}`
                : t("courseDetail.lessonCountShort", { count: chapters.length })}
            </span>
          </CardTitle>
          {!isLocked && (
            <Link
              to={`/courses/${courseId}/modules/${module.id}`}
              className="-my-2 inline-flex shrink-0 sm:my-0"
            >
              <Button variant="ghost" size="sm" className="h-11 text-xs sm:h-7">
                {t("courseDetail.openModule")}
                <ArrowRight className="ml-1 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </Button>
            </Link>
          )}
          {isLocked && (
            <span className="text-xs text-ink-muted flex items-center gap-1">
              <Lock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              {t("courseDetail.moduleLocked")}
            </span>
          )}
        </div>
        {isLocked && isFirstLocked && (
          <p className="text-xs text-ink-muted ml-8 mt-1">
            {t("courseDetail.moduleLockHint")}
          </p>
        )}
        {module.description && (
          <CardDescription className="ml-8 mt-0.5 text-xs text-wrap-safe">
            {module.description}
          </CardDescription>
        )}
        {module.due_date && (() => {
          const dueDate = new Date(module.due_date)
          const now = new Date()
          const overdue = dueDate < now && !allComplete
          return (
            <div
              className={`ml-8 mt-1 flex items-center gap-1 text-xs ${
                overdue ? "text-destructive" : "text-ink-muted"
              }`}
            >
              {overdue ? (
                <AlertTriangle className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              ) : (
                <Clock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              )}
              <span>
                {overdue ? t("courseDetail.overdue") : t("courseDetail.due")}: {formatDate(module.due_date)}
              </span>
            </div>
          )
        })()}
      </CardHeader>
    </Card>
  )
})

interface LessonRowProps {
  courseId: string
  chapter: Chapter
  /** The lesson's place in the course's reading order, 1-based. */
  position: number
  isLocked: boolean
  isFirstLocked: boolean
  /** `null` when the progress request failed. See `moduleProgress.ts`. */
  completedChapterIds: Set<string> | null
}

/**
 * A lesson the outline lists directly, because no module groups it.
 *
 * The whole card is the link — there is nothing else on the row to press,
 * and a lesson is one destination where a module is a page of them.
 */
const LessonRow = memo(function LessonRow({
  courseId,
  chapter,
  position,
  isLocked,
  isFirstLocked,
  completedChapterIds,
}: LessonRowProps) {
  const { t } = useTranslation()
  const isGradable = isGradableChapterType(chapter.chapter_type)
  const complete = isChapterComplete(completedChapterIds, chapter, isGradable)
  const read = isChapterRead(completedChapterIds, chapter, isGradable)

  const body = (
    <Card
      className={`transition-colors ${isLocked ? "opacity-60" : "hover:border-brand/25"}`}
      aria-disabled={isLocked || undefined}
    >
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex min-w-0 flex-1 items-center gap-2 text-sm">
            <RowMarker
              locked={isLocked}
              complete={complete}
              read={read}
              ordinal={position}
              readLabel={t("module.chapterRead")}
            />
            <span className={`min-w-0 flex-1 truncate ${isLocked || complete ? "text-ink-muted" : ""}`}>
              {orNotTranslated(t, chapter.title)}
            </span>
            {chapter.chapter_type && <ChapterTypeBadge type={chapter.chapter_type} size="sm" />}
          </CardTitle>
          {isLocked ? (
            <span className="flex shrink-0 items-center gap-1 text-xs text-ink-muted">
              <Lock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              {t("courseDetail.lessonLocked")}
            </span>
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
          )}
        </div>
        {isLocked && isFirstLocked && (
          <p className="text-xs text-ink-muted ml-8 mt-1">{t("courseDetail.lessonLockHint")}</p>
        )}
      </CardHeader>
    </Card>
  )

  if (isLocked) return body

  return (
    <Link to={chapterHref(courseId, chapter.id)} className="block">
      {body}
    </Link>
  )
})
