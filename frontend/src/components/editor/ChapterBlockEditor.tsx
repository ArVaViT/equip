import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Label } from "@/components/ui/label"
import { Loader2 } from "lucide-react"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import type { ChapterBlock } from "@/types"
import { useConfirm } from "@/components/ui/alert-dialog"
import { AddBlockMenu, BlockRow, type BlockType } from "./blocks"
import { BLOCK_TYPE_LABEL_KEYS } from "./blocks/types"

interface Props {
  courseId: string
  chapterId: string
}

/**
 * Teacher-facing list of content blocks for a chapter. Thin
 * orchestrator: owns the list + which block is expanded + the drag
 * state for reordering, and delegates each row (and every type of
 * per-block editor) to `./blocks/`.
 */
export default function ChapterBlockEditor({ courseId, chapterId }: Props) {
  const confirm = useConfirm()
  const { t } = useTranslation()
  const [blocks, setBlocks] = useState<ChapterBlock[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null)
  // Blocks whose text has not reached the server: typed and still debounced,
  // collapsed with a save in flight, or failed and living only in this
  // browser's draft. Any of them is a reason not to let the page go quietly.
  const [unsavedIds, setUnsavedIds] = useState<ReadonlySet<string>>(() => new Set())

  const markUnsaved = useCallback((blockId: string, unsaved: boolean) => {
    setUnsavedIds((prev) => {
      if (prev.has(blockId) === unsaved) return prev
      const next = new Set(prev)
      if (unsaved) next.add(blockId)
      else next.delete(blockId)
      return next
    })
  }, [])

  // ChapterEditor has its own handler for the chapter's title and type; the
  // two coexist — the browser shows one prompt if either asks for it. This
  // one is about the blocks, which the page-level one knows nothing about.
  const hasUnsaved = unsavedIds.size > 0
  useEffect(() => {
    if (!hasUnsaved) return
    const warnBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener("beforeunload", warnBeforeUnload)
    return () => window.removeEventListener("beforeunload", warnBeforeUnload)
  }, [hasUnsaved])

  const load = useCallback(
    async (signal?: { cancelled: boolean }) => {
      try {
        // Editor-only fetch so the rich-text editor binds to the source
        // `content` (TipTap HTML) regardless of UI locale. A teacher in
        // EN UI editing their RU course would otherwise see the EN
        // translation in the editor and a PATCH would overwrite the
        // source `content` column with English HTML.
        const data = await coursesService.getChapterBlocksForEdit(chapterId)
        if (signal?.cancelled) return
        setBlocks(data.sort((a, b) => a.order_index - b.order_index))
      } catch (error: unknown) {
        if (signal?.cancelled) return
        const detail = getErrorDetail(error)
        if (detail) {
          toast({
            title: t("blockEditor.loadFailed", { detail }),
            variant: "destructive",
          })
        }
      } finally {
        if (!signal?.cancelled) setLoading(false)
      }
    },
    [chapterId, t],
  )

  useEffect(() => {
    const signal = { cancelled: false }
    void load(signal)
    return () => {
      signal.cancelled = true
    }
  }, [load])

  const addBlock = async (type: BlockType) => {
    setAdding(true)
    try {
      const newBlock = await coursesService.createBlock(chapterId, {
        block_type: type,
        order_index: blocks.length,
      })
      setBlocks((prev) => [...prev, newBlock])
      setExpandedId(newBlock.id)
      toast({
        title: t("blockEditor.addedSuccess", { type: t(BLOCK_TYPE_LABEL_KEYS[type]) }),
        variant: "success",
      })
    } catch (error: unknown) {
      const detail = getErrorDetail(error) || t("chapterEditor.unknownError")
      toast({
        title: t("blockEditor.addFailed", { detail }),
        variant: "destructive",
      })
    } finally {
      setAdding(false)
    }
  }

  const replaceBlock = (updated: ChapterBlock) => {
    setBlocks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)))
  }

  const deleteBlock = async (id: string) => {
    const ok = await confirm({
      title: t("blockEditor.confirmDelete.title"),
      // The block's content (text, quiz attempts, file references) is
      // hard-deleted; teachers were getting the minimal dialog with
      // no warning about irreversibility. Now matches the chapter +
      // module delete tone.
      description: t("blockEditor.confirmDelete.description"),
      confirmLabel: t("blockEditor.confirmDelete.confirm"),
      tone: "destructive",
    })
    if (!ok) return
    try {
      await coursesService.deleteBlock(id)
      setBlocks((prev) => prev.filter((b) => b.id !== id))
      if (expandedId === id) setExpandedId(null)
      markUnsaved(id, false)
      toast({ title: t("blockEditor.deleted"), variant: "success" })
    } catch {
      toast({ title: t("blockEditor.deleteFailed"), variant: "destructive" })
    }
  }

  const handleDrop = async (targetIdx: number) => {
    if (dragIdx === null || dragIdx === targetIdx) {
      setDragIdx(null)
      setDragOverIdx(null)
      return
    }
    const reordered = [...blocks]
    const [moved] = reordered.splice(dragIdx, 1)
    if (!moved) return
    reordered.splice(targetIdx, 0, moved)
    const withIndex = reordered.map((b, i) => ({ ...b, order_index: i }))
    setBlocks(withIndex)
    setDragIdx(null)
    setDragOverIdx(null)

    try {
      await coursesService.reorderBlocks(
        chapterId,
        withIndex.map((b) => ({ id: b.id, order_index: b.order_index })),
      )
    } catch {
      toast({ title: t("blockEditor.reorderFailed"), variant: "destructive" })
      void load()
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-ink-muted" strokeWidth={1.75} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">
          {t("blockEditor.contentBlocks")}
        </Label>
        <span className="text-xs text-ink-muted">
          {t("blockEditor.blocksCount", { count: blocks.length })}
        </span>
      </div>

      {blocks.length === 0 && (
        // Inviting empty state instead of a single flat line. The
        // dashed border + soft surface communicates "drop zone /
        // start-here" and reduces the "this UI is broken" reaction
        // when a teacher first sees an empty chapter.
        <div className="rounded-md border border-dashed border-edge bg-muted/30 px-5 py-8 text-center">
          <p className="text-sm font-medium text-ink">
            {t("blockEditor.empty")}
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            {t("blockEditor.emptyHint")}
          </p>
        </div>
      )}

      <div className="space-y-2">
        {blocks.map((block, idx) => (
          <BlockRow
            key={block.id}
            block={block}
            courseId={courseId}
            chapterId={chapterId}
            index={idx}
            expanded={expandedId === block.id}
            isDragOver={dragOverIdx === idx}
            onExpandToggle={() =>
              setExpandedId((prev) => (prev === block.id ? null : block.id))
            }
            onDelete={() => deleteBlock(block.id)}
            onBlockUpdated={replaceBlock}
            onUnsavedChange={(unsaved) => markUnsaved(block.id, unsaved)}
            onDragStart={() => setDragIdx(idx)}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOverIdx(idx)
            }}
            onDrop={() => handleDrop(idx)}
            onDragEnd={() => {
              setDragIdx(null)
              setDragOverIdx(null)
            }}
          />
        ))}
      </div>

      <AddBlockMenu onAdd={addBlock} adding={adding} />
    </div>
  )
}
