import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { ChevronDown, ChevronRight, GripVertical, Trash2 } from "lucide-react"
import QuizEditor from "@/components/quiz/QuizEditor"
import AssignmentEditor from "@/components/assignment/AssignmentEditor"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { ChapterBlock } from "@/types"
import { blockIcon } from "./types"
import { TextBlockEditor } from "./TextBlockEditor"
import { FileBlockEditor } from "./FileBlockEditor"

interface Props {
  block: ChapterBlock
  chapterId: string
  index: number
  expanded: boolean
  isDragOver: boolean
  onExpandToggle: () => void
  onDelete: () => void
  onBlockUpdated: (updated: ChapterBlock) => void
  onDragStart: () => void
  onDragOver: (e: React.DragEvent) => void
  onDrop: () => void
  onDragEnd: () => void
}

/**
 * A single draggable chapter block: drag handle, expand/collapse
 * header, delete button, and a type-specific editor body when expanded.
 */
export function BlockRow({
  block,
  chapterId,
  index,
  expanded,
  isDragOver,
  onExpandToggle,
  onDelete,
  onBlockUpdated,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: Props) {
  const { t } = useTranslation()
  const Icon = blockIcon(block.block_type)
  const label = t(`blockEditor.types.${block.block_type}`, { defaultValue: block.block_type })

  const updateField = async (field: string, value: string) => {
    try {
      const updated = await coursesService.updateBlock(block.id, { [field]: value })
      onBlockUpdated(updated)
    } catch {
      toast({ title: t("blockEditor.updateFailed"), variant: "destructive" })
    }
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      className={`rounded-md border transition-colors ${
        isDragOver ? "border-primary bg-primary/5" : "bg-background"
      }`}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none"
        onClick={onExpandToggle}
      >
        <GripVertical className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0 cursor-grab" />
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        )}
        <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="text-sm font-medium flex-1">{label}</span>
        <span className="text-[10px] text-muted-foreground">#{index + 1}</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0 text-destructive hover:text-destructive shrink-0"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>

      {expanded && (
        <div className="border-t px-3 py-3 space-y-3">
          {block.block_type === "text" && (
            <TextBlockEditor block={block} onSaved={onBlockUpdated} />
          )}
          {block.block_type === "quiz" && (
            <QuizEditor
              chapterId={chapterId}
              onQuizSaved={(quizId) => updateField("quiz_id", quizId)}
            />
          )}
          {block.block_type === "assignment" && (
            <AssignmentEditor
              chapterId={chapterId}
              onAssignmentCreated={(id) => updateField("assignment_id", id)}
            />
          )}
          {block.block_type === "file" && (
            <FileBlockEditor
              block={block}
              chapterId={chapterId}
              onUpdated={onBlockUpdated}
            />
          )}
        </div>
      )}
    </div>
  )
}
