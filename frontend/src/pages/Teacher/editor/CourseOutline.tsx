import type { HTMLAttributes } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  DragDropContext,
  Draggable,
  Droppable,
  type DropResult,
} from "@hello-pangea/dnd"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { EmptyState } from "@/components/patterns"
import { BookOpen, GripVertical, Layers, MoreHorizontal, Trash2 } from "lucide-react"
import { AddChapterBar } from "../chapters/AddChapterBar"
import { ChapterList } from "../chapters/ChapterList"
import type { ChapterMove } from "../chapters/ChapterRow"
import { chapterEditHref, type CourseStructure } from "@/lib/courseStructure"
import type { ChapterType } from "@/lib/chapterTypes"
import type { Chapter, Module } from "@/types"

interface Props {
  courseId: string
  /** The course read once — the outline to draw and the reading order. */
  structure: CourseStructure
  /** Modules in order. Empty for a course that groups nothing. */
  modules: Module[]
  onModuleDragEnd: (result: DropResult) => void
  onChapterDragEnd: (result: DropResult) => void
  onAddModule: () => void
  onAddChapter: (type: ChapterType) => void
  onRemoveModule: (id: string) => void
  onChapterTitleChange: (chapterId: string, title: string) => void
  onRenameChapter: (chapter: Chapter, title: string) => void
  onToggleChapterLock: (chapter: Chapter) => void
  onDeleteChapter: (chapterId: string) => void
  onMoveChapter: (chapterId: string, moduleId: string | null) => void
}

/**
 * What the course is made of, as the teacher sees it.
 *
 * This used to be a list of modules with one button on it, "Add module",
 * and a lesson could only be reached by going through one. A teacher whose
 * course is four lessons had to invent a heading to hold them — the first
 * one to try reshaped his course twice and then deleted the lessons.
 *
 * So the list is lessons and modules together, in the order
 * `readCourseStructure` reads them (modules first, then the lessons that
 * are in no module), and the button on it adds a **lesson**, straight into
 * the course. Grouping is still there for a course that wants parts, but
 * it has moved into the overflow menu where an offer belongs — a teacher
 * who never needs a module never has to read the word.
 */
export function CourseOutline({
  courseId,
  structure,
  modules,
  onModuleDragEnd,
  onChapterDragEnd,
  onAddModule,
  onAddChapter,
  onRemoveModule,
  onChapterTitleChange,
  onRenameChapter,
  onToggleChapterLock,
  onDeleteChapter,
  onMoveChapter,
}: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation()

  // The tail group — the lessons that are in no module. `readCourseStructure`
  // only appends it when it has something in it, so its absence means every
  // lesson is grouped.
  const ungrouped = structure.groups.find((g) => g.moduleId === null)?.chapters ?? []
  const isEmpty = structure.chapters.length === 0 && modules.length === 0

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

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-serif text-xl font-semibold flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-brand" strokeWidth={1.75} />
          {t("teacherEditor.contentHeading")}
        </h2>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              aria-label={t("teacherEditor.outlineMenuAria")}
            >
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
          {modules.length > 0 && (
            <DragDropContext onDragEnd={onModuleDragEnd}>
              <Droppable droppableId="modules">
                {(provided) => (
                  <div
                    className="space-y-2 mb-3"
                    ref={provided.innerRef}
                    {...provided.droppableProps}
                  >
                    {modules.map((mod, i) => (
                      <Draggable key={mod.id} draggableId={mod.id} index={i}>
                        {(dragProvided, snapshot) => (
                          <Card
                            ref={dragProvided.innerRef}
                            // dnd draggableProps are valid div attrs at runtime; cast
                            // satisfies the stricter CSSProperties in newer @types/react.
                            {...(dragProvided.draggableProps as HTMLAttributes<HTMLDivElement>)}
                            className={`group flex items-center gap-3 p-4 hover:bg-muted/40 transition-colors cursor-pointer ${
                              snapshot.isDragging ? "shadow-lg ring-2 ring-primary/20" : ""
                            }`}
                            onClick={() =>
                              navigate(`/teacher/courses/${courseId}/modules/${mod.id}/edit`)
                            }
                          >
                            <div
                              {...dragProvided.dragHandleProps}
                              className="-ml-2 flex h-11 w-8 shrink-0 cursor-grab items-center justify-center text-ink-muted transition-colors hover:text-ink active:cursor-grabbing sm:h-9"
                              onClick={(e) => e.stopPropagation()}
                              role="button"
                              tabIndex={0}
                              aria-label={t("teacherEditor.dragModuleAria", { title: mod.title })}
                            >
                              <GripVertical className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                            </div>
                            <Layers
                              className="h-4 w-4 shrink-0 text-ink-muted"
                              strokeWidth={1.75}
                              aria-hidden
                            />
                            <div className="flex-1 min-w-0">
                              <p className="font-medium truncate">{mod.title}</p>
                              <p className="text-xs text-ink-muted mt-0.5">
                                {t("teacherEditor.lessonCount", {
                                  count: mod.chapters?.length ?? 0,
                                })}
                              </p>
                            </div>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-11 w-11 shrink-0 p-0 text-destructive opacity-100 transition-opacity hover:text-destructive sm:h-9 sm:w-9 sm:opacity-60 sm:group-hover:opacity-100"
                              onClick={(e) => {
                                e.stopPropagation()
                                onRemoveModule(mod.id)
                              }}
                              aria-label={t("teacherEditor.deleteModuleAria", { title: mod.title })}
                            >
                              <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                            </Button>
                          </Card>
                        )}
                      </Draggable>
                    ))}
                    {provided.placeholder}
                  </div>
                )}
              </Droppable>
            </DragDropContext>
          )}

          {ungrouped.length > 0 && (
            <ChapterList
              chapters={ungrouped}
              droppableId="course-chapters"
              onDragEnd={onChapterDragEnd}
              onTitleChange={onChapterTitleChange}
              onRename={onRenameChapter}
              onToggleLock={onToggleChapterLock}
              onEdit={(chapterId) => navigate(chapterEditHref(courseId, chapterId))}
              onDelete={onDeleteChapter}
              moveFor={moveFor}
            />
          )}

          <AddChapterBar onAdd={onAddChapter} variant="compact" />
        </>
      )}
    </>
  )
}
