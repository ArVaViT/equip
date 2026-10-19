import { useState, type HTMLAttributes } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { DragDropContext, Draggable, Droppable, type DropResult } from "@hello-pangea/dnd"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { EmptyState } from "@/components/patterns"
import { BookOpen, ChevronDown, GripVertical, Layers, MoreHorizontal, Settings2, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { AddChapterBar } from "../chapters/AddChapterBar"
import { ChapterList } from "../chapters/ChapterList"
import { ChapterRow, type ChapterMove } from "../chapters/ChapterRow"
import { chapterEditHref, outlinePlaces, type CourseStructure } from "@/lib/courseStructure"
import type { ChapterType } from "@/lib/chapterTypes"
import type { Chapter } from "@/types"

interface Props {
  courseId: string
  /** The course read once — the outline to draw and the reading order. */
  structure: CourseStructure
  /** A drag among the course's places: modules and lessons outside them. */
  onOutlineDragEnd: (result: DropResult) => void
  onAddModule: () => void
  onAddChapter: (type: ChapterType, moduleId?: string | null) => void
  /** Reorder inside one module, from its expanded list here. */
  onModuleChapterDragEnd: (moduleId: string, result: DropResult) => void
  onRemoveModule: (id: string) => void
  onChapterTitleChange: (chapterId: string, title: string) => void
  onRenameChapter: (chapter: Chapter, title: string, previous: string) => void
  onToggleChapterLock: (chapter: Chapter) => void
  onDeleteChapter: (chapterId: string) => void
  onMoveChapter: (chapterId: string, moduleId: string | null) => void
}

/** The drop type of the course's places — modules and loose lessons. */
const OUTLINE = "outline"
/** Prefix of the drop type of one module's own lessons; the module id follows. */
const LESSONS_OF = "lessons-of-"

/**
 * What the course is made of, as the teacher sees it.
 *
 * This used to be a list of modules with one button on it, "Add module",
 * and a lesson could only be reached by going through one. A teacher whose
 * course is four lessons had to invent a heading to hold them — the first
 * one to try reshaped his course twice and then deleted the lessons.
 *
 * So the list is lessons and modules together, in one sequence — the order
 * the teacher sets here is the order the student reads (2026-10-16). A
 * lesson outside modules sits where it was put, between modules if that is
 * where it went, and drags among the modules like one. The button on the
 * list adds a **lesson**, straight into the course. Grouping is still there
 * for a course that wants parts, but it has moved into the overflow menu
 * where an offer belongs — a teacher who never needs a module never has to
 * read the word.
 */
export function CourseOutline({
  courseId,
  structure,
  onOutlineDragEnd,
  onAddModule,
  onAddChapter,
  onModuleChapterDragEnd,
  onRemoveModule,
  onChapterTitleChange,
  onRenameChapter,
  onToggleChapterLock,
  onDeleteChapter,
  onMoveChapter,
}: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation()

  const places = outlinePlaces(structure)
  const modules = structure.groups.flatMap((g) => (g.module ? [g.module] : []))
  const isEmpty = places.length === 0

  // One drag context for the whole outline. The places drag among each
  // other; a module's own lessons drag inside their module's list, kept
  // there by the list's type.
  const onDragEnd = (result: DropResult) => {
    if (result.type === OUTLINE) onOutlineDragEnd(result)
    else if (result.type.startsWith(LESSONS_OF)) onModuleChapterDragEnd(result.type.slice(LESSONS_OF.length), result)
  }

  /**
   * Where a loose lesson can go. Never `canUngroup` — it is already out of
   * every module — and an empty `intoModules` (a course with no modules at
   * all) makes the row render no move control whatsoever.
   */
  const moveFor = (chapter: Chapter): ChapterMove => ({
    intoModules: modules.map((m) => ({ id: m.id, title: m.title })),
    canUngroup: false,
    onMove: (moduleId) => onMoveChapter(chapter.id, moduleId),
  })

  /** A lesson in a module: to any other module, or out into the course. */
  const moveFromModule =
    (moduleId: string) =>
    (chapter: Chapter): ChapterMove => ({
      intoModules: modules.filter((m) => m.id !== moduleId).map((m) => ({ id: m.id, title: m.title })),
      canUngroup: true,
      onMove: (target) => onMoveChapter(chapter.id, target),
    })

  // Modules open on the course page itself. A module used to be a card
  // with a number on it — «4 lessons» — and every lesson in it was a page
  // away, so moving one from a module to the next took two trips. Open,
  // a module shows its lessons with everything a lesson row can do, and
  // its own "add a lesson" line; the module's name and description are
  // still edited on its page (the gear).
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set())
  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const chaptersOf = (moduleId: string) => structure.groups.find((g) => g.moduleId === moduleId)?.chapters ?? []

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-serif text-xl font-semibold flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-brand" strokeWidth={1.75} />
          {t("teacherEditor.contentHeading")}
        </h2>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" aria-label={t("teacherEditor.outlineMenuAria")}>
              <MoreHorizontal className="h-4 w-4" strokeWidth={1.75} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[16rem]">
            <DropdownMenuItem onSelect={onAddModule}>
              <Layers className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("teacherEditor.addModule")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {isEmpty ? (
        <EmptyState
          icon={<BookOpen strokeWidth={1.75} />}
          title={t("teacherEditor.empty.title")}
          description={t("teacherEditor.empty.description")}
          action={<AddChapterBar onAdd={onAddChapter} variant="empty" />}
          className="mb-6"
        />
      ) : (
        <>
          <DragDropContext onDragEnd={onDragEnd}>
            <Droppable droppableId="outline" type={OUTLINE}>
              {(provided) => (
                <div className="mb-3 space-y-2" ref={provided.innerRef} {...provided.droppableProps}>
                  {places.map((place, i) => {
                    if (place.kind === "lesson") {
                      const ch = place.chapter
                      return (
                        <ChapterRow
                          key={ch.id}
                          chapter={ch}
                          index={i}
                          onTitleChange={(title) => onChapterTitleChange(ch.id, title)}
                          onRename={(title, previous) => onRenameChapter(ch, title, previous)}
                          onToggleLock={() => onToggleChapterLock(ch)}
                          onEdit={() => navigate(chapterEditHref(courseId, ch.id))}
                          onDelete={() => onDeleteChapter(ch.id)}
                          move={moveFor(ch)}
                        />
                      )
                    }
                    const mod = place.module
                    return (
                      <Draggable key={mod.id} draggableId={mod.id} index={i}>
                        {(dragProvided, snapshot) => (
                          <Card
                            ref={dragProvided.innerRef}
                            {...(dragProvided.draggableProps as HTMLAttributes<HTMLDivElement>)}
                            className={cn(
                              "group overflow-hidden transition-colors",
                              snapshot.isDragging && "shadow-lg ring-2 ring-primary/20",
                            )}
                          >
                            <div className="flex items-center gap-3 p-4">
                              <div
                                {...dragProvided.dragHandleProps}
                                className="-ml-2 flex h-11 w-8 shrink-0 cursor-grab items-center justify-center text-ink-muted transition-colors hover:text-ink active:cursor-grabbing sm:h-9"
                                role="button"
                                tabIndex={0}
                                aria-label={t("teacherEditor.dragModuleAria", {
                                  title: mod.title,
                                })}
                              >
                                <GripVertical className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                              </div>
                              <button
                                type="button"
                                onClick={() => toggle(mod.id)}
                                aria-expanded={open.has(mod.id)}
                                className="flex min-w-0 flex-1 items-center gap-3 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                              >
                                <Layers className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                                <span className="min-w-0 flex-1">
                                  {/* Two lines on a phone: one showed «Модуль 1…» and no more. */}
                                  <span className="line-clamp-2 font-medium sm:line-clamp-1">{mod.title}</span>
                                  <span className="mt-0.5 block text-xs text-ink-muted">
                                    {t("teacherEditor.lessonCount", {
                                      count: mod.chapters?.length ?? 0,
                                    })}
                                  </span>
                                </span>
                                <ChevronDown
                                  className={cn(
                                    "h-4 w-4 shrink-0 text-ink-muted transition-transform duration-base",
                                    open.has(mod.id) && "rotate-180",
                                  )}
                                  strokeWidth={1.75}
                                  aria-hidden
                                />
                              </button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-11 w-9 shrink-0 p-0 text-ink-muted hover:text-ink sm:h-9 sm:w-9"
                                onClick={() => navigate(`/teacher/courses/${courseId}/modules/${mod.id}/edit`)}
                                aria-label={t("teacherEditor.openModuleAria", {
                                  title: mod.title,
                                })}
                                title={t("teacherEditor.openModuleAria", {
                                  title: mod.title,
                                })}
                              >
                                <Settings2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-11 w-9 shrink-0 p-0 text-ink-muted transition-colors hover:text-destructive sm:h-9 sm:w-9"
                                onClick={() => onRemoveModule(mod.id)}
                                aria-label={t("teacherEditor.deleteModuleAria", { title: mod.title })}
                              >
                                <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                              </Button>
                            </div>
                            {open.has(mod.id) && (
                              <div className="border-t border-edge bg-muted/10 px-3 pb-3 pt-3 sm:px-4">
                                {chaptersOf(mod.id).length > 0 && (
                                  <ChapterList
                                    chapters={chaptersOf(mod.id)}
                                    droppableId={`module-${mod.id}`}
                                    nested={{ type: `${LESSONS_OF}${mod.id}` }}
                                    onDragEnd={(result) => onModuleChapterDragEnd(mod.id, result)}
                                    onTitleChange={onChapterTitleChange}
                                    onRename={onRenameChapter}
                                    onToggleLock={onToggleChapterLock}
                                    onEdit={(chapterId) => navigate(chapterEditHref(courseId, chapterId))}
                                    onDelete={onDeleteChapter}
                                    moveFor={moveFromModule(mod.id)}
                                  />
                                )}
                                <AddChapterBar onAdd={(type) => onAddChapter(type, mod.id)} variant="compact" />
                              </div>
                            )}
                          </Card>
                        )}
                      </Draggable>
                    )
                  })}
                  {provided.placeholder}
                </div>
              )}
            </Droppable>
          </DragDropContext>

          <AddChapterBar onAdd={onAddChapter} variant="compact" />
        </>
      )}
    </>
  )
}
