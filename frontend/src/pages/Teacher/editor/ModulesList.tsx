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
import { EmptyState } from "@/components/patterns"
import { GripVertical, Layers, Plus, Trash2 } from "lucide-react"
import type { Module } from "@/types"

interface Props {
  courseId: string
  modules: Module[]
  onDragEnd: (result: DropResult) => void
  onAdd: () => void
  onRemove: (id: string) => void
}

/** Sortable module list for the course editor. */
export function ModulesList({ courseId, modules, onDragEnd, onAdd, onRemove }: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation()

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-serif text-xl font-semibold flex items-center gap-2">
          <Layers className="h-5 w-5 text-primary/60" strokeWidth={1.75} />
          {t("teacherEditor.modulesHeading")}
        </h2>
        <Button onClick={onAdd} size="sm" variant="outline">
          <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
          {t("teacherEditor.addModule")}
        </Button>
      </div>

      {modules.length === 0 ? (
        <EmptyState
          icon={<Layers strokeWidth={1.75} />}
          title={t("teacherEditor.noModulesYet")}
          description={t("teacherEditor.noModulesYetDescription")}
          action={
            <Button onClick={onAdd} size="sm">
              <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
              {t("teacherEditor.addModule")}
            </Button>
          }
        />
      ) : (
        <DragDropContext onDragEnd={onDragEnd}>
          <Droppable droppableId="modules">
            {(provided) => (
              <div
                className="space-y-2"
                ref={provided.innerRef}
                {...provided.droppableProps}
              >
                {modules.map((mod, i) => (
                  <Draggable key={mod.id} draggableId={mod.id} index={i}>
                    {(dragProvided, snapshot) => (
                      <Card
                        ref={dragProvided.innerRef}
                        {...dragProvided.draggableProps}
                        className={`group flex items-center gap-3 p-4 hover:bg-muted/40 transition-colors cursor-pointer ${
                          snapshot.isDragging ? "shadow-lg ring-2 ring-primary/20" : ""
                        }`}
                        onClick={() =>
                          navigate(`/teacher/courses/${courseId}/modules/${mod.id}/edit`)
                        }
                      >
                        <div
                          {...dragProvided.dragHandleProps}
                          className="cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-muted-foreground shrink-0 transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <GripVertical className="h-4 w-4" strokeWidth={1.75} />
                        </div>
                        <span className="text-xs font-mono text-muted-foreground/50 w-6 text-right shrink-0">
                          {i + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">{mod.title}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {t("teacherEditor.chapterCount", {
                              count: mod.chapters?.length ?? 0,
                            })}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="opacity-60 group-hover:opacity-100 text-destructive hover:text-destructive shrink-0 transition-opacity"
                          onClick={(e) => {
                            e.stopPropagation()
                            onRemove(mod.id)
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
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
    </>
  )
}
