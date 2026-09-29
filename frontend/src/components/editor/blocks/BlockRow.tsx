import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, GripVertical, Trash2 } from "lucide-react"
import QuizEditor from "@/components/quiz/QuizEditor"
import AssignmentEditor from "@/components/assignment/AssignmentEditor"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { ChapterBlock } from "@/types"
import { blockIcon } from "./types"
import { TextBlockEditor } from "./TextBlockEditor"
import { FileBlockEditor } from "./FileBlockEditor"

/** The first words of a block, for its folded header. */
function blockPreview(block: ChapterBlock): string {
  const raw = block.content ?? block.file_name ?? ""
  if (!raw) return ""
  const text = raw.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim()
  return text.length > 90 ? `${text.slice(0, 90)}…` : text
}

interface Props {
  block: ChapterBlock
  courseId: string
  chapterId: string
  index: number
  expanded: boolean
  isDragOver: boolean
  onExpandToggle: () => void
  /** One step up / down; absent at the ends. For touch, where drag does not work. */
  onMoveUp?: () => void
  onMoveDown?: () => void
  onDelete: () => void
  onBlockUpdated: (updated: ChapterBlock) => void
  /** The block's editor holds text the server does not have yet (or no longer does). */
  onUnsavedChange?: (unsaved: boolean) => void
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
  courseId,
  chapterId,
  index,
  expanded,
  isDragOver,
  onExpandToggle,
  onMoveUp,
  onMoveDown,
  onDelete,
  onBlockUpdated,
  onUnsavedChange,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: Props) {
  const { t } = useTranslation()
  const Icon = blockIcon(block.block_type)
  const label = t(`blockEditor.types.${block.block_type}`, { defaultValue: block.block_type })
  // What the block says, for its header when folded: «Текст #1» told a
  // teacher nothing about which of six text blocks was which.
  const preview = blockPreview(block)

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
        isDragOver ? "border-brand bg-brand/5" : "bg-surface"
      }`}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none"
        onClick={onExpandToggle}
      >
        <GripVertical className="h-3.5 w-3.5 text-ink-muted shrink-0 cursor-grab" strokeWidth={1.75} />
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-ink-muted shrink-0" strokeWidth={1.75} />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-ink-muted shrink-0" strokeWidth={1.75} />
        )}
        <Icon className="h-3.5 w-3.5 text-ink-muted shrink-0" />
        <span className="shrink-0 text-sm font-medium">{label}</span>
        <span className="min-w-0 flex-1 truncate text-xs text-ink-muted">
          {!expanded && preview ? preview : `#${index + 1}`}
        </span>
        {[
          { run: onMoveUp, Icon: ArrowUp, key: "blockEditor.moveUp" },
          { run: onMoveDown, Icon: ArrowDown, key: "blockEditor.moveDown" },
        ].map(({ run, Icon: MoveIcon, key }) => (
          <Button
            key={key}
            variant="ghost"
            size="sm"
            className="h-9 w-9 shrink-0 p-0 text-ink-muted sm:h-7 sm:w-7"
            disabled={!run}
            onClick={(e) => {
              e.stopPropagation()
              run?.()
            }}
            aria-label={t(key, { label })}
            title={t(key, { label })}
          >
            <MoveIcon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          </Button>
        ))}
        <Button
          variant="ghost"
          size="sm"
          className="h-9 w-9 shrink-0 p-0 text-ink-muted transition-colors hover:text-destructive sm:h-7 sm:w-7"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          aria-label={t("blockEditor.deleteBlockAria", { label })}
        >
          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
        </Button>
      </div>

      {expanded && (
        <div className="border-t px-3 py-3 space-y-3">
          {block.block_type === "text" && (
            <TextBlockEditor
              block={block}
              onSaved={onBlockUpdated}
              onUnsavedChange={onUnsavedChange}
            />
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
              courseId={courseId}
              onAssignmentCreated={(id) => updateField("assignment_id", id)}
            />
          )}
          {block.block_type === "file" && (
            <FileBlockEditor
              block={block}
              courseId={courseId}
              chapterId={chapterId}
              onUpdated={onBlockUpdated}
            />
          )}
        </div>
      )}
    </div>
  )
}
