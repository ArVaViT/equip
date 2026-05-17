import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Check, Loader2, Save } from "lucide-react"
import RichTextEditor from "../RichTextEditor"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { ChapterBlock } from "@/types"

interface Props {
  block: ChapterBlock
  onSaved: (updated: ChapterBlock) => void
}

type AutoSaveStatus = "idle" | "pending" | "saving" | "saved"

const AUTOSAVE_DELAY_MS = 2000
const SAVED_FLASH_MS = 2000

/**
 * Rich-text content editor for a `text` chapter block. Owns its own
 * draft state + debounced auto-save pipeline; deactivates when the
 * browser tab is hidden so background tabs don't hammer the API.
 */
export function TextBlockEditor({ block, onSaved }: Props) {
  const { t } = useTranslation()
  const [content, setContent] = useState(block.content ?? "")
  const [savingExplicit, setSavingExplicit] = useState(false)
  const [autoSaveStatus, setAutoSaveStatus] = useState<AutoSaveStatus>("idle")

  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savedResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const contentRef = useRef(content)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
      if (savedResetTimer.current) clearTimeout(savedResetTimer.current)
    }
  }, [])

  const scheduleAutoSave = () => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    if (savedResetTimer.current) clearTimeout(savedResetTimer.current)
    setAutoSaveStatus("pending")
    const snapshot = contentRef.current
    autoSaveTimer.current = setTimeout(async () => {
      if (!mountedRef.current) return
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        setAutoSaveStatus("pending")
        return
      }
      setAutoSaveStatus("saving")
      try {
        const updated = await coursesService.updateBlock(block.id, { content: snapshot })
        if (!mountedRef.current) return
        onSaved(updated)
        setAutoSaveStatus("saved")
        savedResetTimer.current = setTimeout(() => {
          if (mountedRef.current) setAutoSaveStatus("idle")
        }, SAVED_FLASH_MS)
      } catch {
        if (!mountedRef.current) return
        setAutoSaveStatus("idle")
        toast({ title: t("blockEditor.text.autoSaveFailed"), variant: "destructive" })
      }
    }, AUTOSAVE_DELAY_MS)
  }

  const saveExplicit = async () => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    if (savedResetTimer.current) clearTimeout(savedResetTimer.current)
    setAutoSaveStatus("idle")
    setSavingExplicit(true)
    try {
      const updated = await coursesService.updateBlock(block.id, { content })
      onSaved(updated)
      toast({ title: t("blockEditor.text.saved"), variant: "success" })
    } catch {
      toast({ title: t("blockEditor.text.saveFailed"), variant: "destructive" })
    } finally {
      setSavingExplicit(false)
    }
  }

  return (
    <>
      <RichTextEditor
        content={content}
        onChange={(html) => {
          setContent(html)
          contentRef.current = html
          scheduleAutoSave()
        }}
        placeholder={t("blockEditor.text.placeholder")}
      />
      <div className="flex items-center gap-3">
        <Button size="sm" onClick={saveExplicit} disabled={savingExplicit}>
          {savingExplicit ? (
            <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" strokeWidth={1.75} />
          ) : (
            <Save className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
          )}
          {t("blockEditor.text.saveButton")}
        </Button>
        {autoSaveStatus === "pending" && (
          <span className="text-xs text-muted-foreground">
            {t("blockEditor.text.statusUnsaved")}
          </span>
        )}
        {autoSaveStatus === "saving" && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
            {t("blockEditor.text.statusAutoSaving")}
          </span>
        )}
        {autoSaveStatus === "saved" && (
          <span className="flex items-center gap-1 text-xs text-success">
            <Check className="h-3 w-3" strokeWidth={1.75} />
            {t("blockEditor.text.statusSaved")}
          </span>
        )}
      </div>
    </>
  )
}
