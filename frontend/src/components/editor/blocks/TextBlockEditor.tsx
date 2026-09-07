import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { AlertTriangle, Check, Loader2, Save } from "lucide-react"
import RichTextEditor from "../RichTextEditor"
import api from "@/services/api"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import { useLocalDraft } from "@/hooks/useLocalDraft"
import { blockDraftKey } from "@/lib/storageKeys"
import { toast } from "@/lib/toast"
import type { ChapterBlock } from "@/types"

interface Props {
  block: ChapterBlock
  onSaved: (updated: ChapterBlock) => void
  /**
   * Whether this block holds text the server does not have yet. Stays `true`
   * through a save that is still in flight after the editor itself has been
   * closed, and through a failed one — the parent uses it to warn before the
   * page is left.
   */
  onUnsavedChange?: (unsaved: boolean) => void
}

type AutoSaveStatus = "idle" | "pending" | "saving" | "saved" | "failed"

const AUTOSAVE_DELAY_MS = 2000
const SAVED_FLASH_MS = 2000
/** Retry schedule after a failed save. Capped, but it does not give up: the
 *  text at stake is the teacher's, and one request every half-minute is
 *  nothing to the server. */
const RETRY_DELAYS_MS = [2000, 5000, 10000, 20000, 30000]

/**
 * Saves still in flight for blocks whose editor has been closed, by block id,
 * resolving to the content that reached the server (or `null` on failure).
 * A re-opened editor waits for its block's entry before saving so two PUTs
 * for one block can never overtake each other, and adopts the result if the
 * teacher has not typed anything in the meantime.
 */
const inflightByBlock = new Map<string, Promise<string | null>>()

/** TipTap's empty document, with or without the wrapper paragraph. */
function isBlank(html: string): boolean {
  const trimmed = html.trim()
  return trimmed === "" || trimmed === "<p></p>"
}

/**
 * Rich-text content editor for a `text` chapter block. Owns its own
 * draft state and the whole "does this text reach the server" pipeline.
 *
 * The invariant this component exists to keep is simple: **text that was
 * typed or pasted here is never lost silently.** It used to be — a debounced
 * save was thrown away when the block was collapsed, skipped for good when
 * the tab was hidden at the moment the timer fired, and forgotten after a
 * network error. Each of those is now a save, a retry, or at the very least
 * a draft in `localStorage` that is offered back the next time the block is
 * opened.
 */
export function TextBlockEditor({ block, onSaved, onUnsavedChange }: Props) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [content, setContent] = useState(block.content ?? "")
  const [savingExplicit, setSavingExplicit] = useState(false)
  const [autoSaveStatus, setAutoSaveStatus] = useState<AutoSaveStatus>("idle")
  const [draftOffer, setDraftOffer] = useState<string | null>(null)

  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savedResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** What is on screen right now. */
  const contentRef = useRef(content)
  /** What the server has, as far as we know. `dirty` is the gap between the two. */
  const savedRef = useRef(block.content ?? "")
  const mountedRef = useRef(true)
  const savingRef = useRef(false)
  const failuresRef = useRef(0)
  // Latest props for code that outlives a render: the detached save after
  // unmount, the retry timer, the visibility handler.
  const onSavedRef = useRef(onSaved)
  const onUnsavedChangeRef = useRef(onUnsavedChange)
  const tRef = useRef(t)
  useEffect(() => {
    onSavedRef.current = onSaved
    onUnsavedChangeRef.current = onUnsavedChange
    tRef.current = t
  })

  const isDirty = useCallback(() => contentRef.current !== savedRef.current, [])
  const reportUnsaved = useCallback(
    (unsaved: boolean) => onUnsavedChangeRef.current?.(unsaved),
    [],
  )

  const { restored, clear: clearDraft } = useLocalDraft(
    user ? blockDraftKey(user.id, block.id) : null,
    content,
    { restoreInto: "any" },
  )

  const clearTimers = useCallback(() => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    if (savedResetTimer.current) clearTimeout(savedResetTimer.current)
    autoSaveTimer.current = null
    savedResetTimer.current = null
  }, [])

  /**
   * The one place a PUT for this block is issued while the editor is open.
   * Idempotent on the dirty flag: calling it when nothing changed is a no-op,
   * calling it during another save just lets that save re-check on return.
   */
  const performSave = useCallback(
    async ({ explicit = false }: { explicit?: boolean } = {}) => {
      if (savingRef.current) return
      if (!isDirty()) {
        // Nothing the server lacks. The explicit button still deserves an
        // answer — silence after a click reads as a broken button.
        if (mountedRef.current) setAutoSaveStatus("idle")
        if (explicit) toast({ title: tRef.current("blockEditor.text.saved"), variant: "success" })
        return
      }
      savingRef.current = true
      // A save the previous instance of this editor left running must land
      // first — otherwise ours could be overtaken by older content.
      const previous = inflightByBlock.get(block.id)
      if (previous) await previous
      const snapshot = contentRef.current
      if (mountedRef.current) setAutoSaveStatus("saving")
      try {
        const updated = await coursesService.updateBlock(block.id, { content: snapshot })
        savedRef.current = snapshot
        failuresRef.current = 0
        onSavedRef.current(updated)
        if (!mountedRef.current) {
          reportUnsaved(isDirty())
          return
        }
        if (explicit) toast({ title: tRef.current("blockEditor.text.saved"), variant: "success" })
        if (isDirty()) {
          // Typed during the round trip: the debounce owns the rest.
          setAutoSaveStatus("pending")
          scheduleAutoSaveRef.current()
        } else {
          reportUnsaved(false)
          clearDraft()
          setAutoSaveStatus("saved")
          savedResetTimer.current = setTimeout(() => {
            if (mountedRef.current) setAutoSaveStatus("idle")
          }, SAVED_FLASH_MS)
        }
      } catch {
        failuresRef.current += 1
        if (!mountedRef.current) return
        setAutoSaveStatus("failed")
        if (explicit) {
          toast({ title: tRef.current("blockEditor.text.saveFailed"), variant: "destructive" })
        } else if (failuresRef.current === 1) {
          // Once per streak. Every retry after that shows in the status line;
          // a toast every ten seconds would be noise over a working editor.
          toast({
            title: tRef.current("blockEditor.text.autoSaveFailed"),
            description: tRef.current("blockEditor.text.autoSaveFailedHint"),
            variant: "destructive",
          })
        }
        const delay =
          RETRY_DELAYS_MS[Math.min(failuresRef.current, RETRY_DELAYS_MS.length) - 1] ??
          RETRY_DELAYS_MS[RETRY_DELAYS_MS.length - 1]
        scheduleAutoSaveRef.current(delay)
      } finally {
        savingRef.current = false
      }
    },
    [block.id, clearDraft, isDirty, reportUnsaved],
  )

  const scheduleAutoSave = useCallback(
    (delay: number = AUTOSAVE_DELAY_MS) => {
      clearTimers()
      autoSaveTimer.current = setTimeout(() => {
        autoSaveTimer.current = null
        if (!mountedRef.current) return
        // No visibility check here on purpose. A hidden tab is the normal
        // state of an editor while the teacher copies the next paragraph
        // out of Word, and a save skipped "until the tab is visible" was
        // in practice a save that never happened.
        void performSave()
      }, delay)
    },
    [clearTimers, performSave],
  )
  const scheduleAutoSaveRef = useRef(scheduleAutoSave)
  useEffect(() => {
    scheduleAutoSaveRef.current = scheduleAutoSave
  }, [scheduleAutoSave])

  const applyContent = useCallback(
    (html: string) => {
      setContent(html)
      contentRef.current = html
      if (isDirty()) {
        reportUnsaved(true)
        setAutoSaveStatus("pending")
        scheduleAutoSave()
      } else {
        // Typed back to exactly what the server has — nothing to send.
        clearTimers()
        reportUnsaved(false)
        setAutoSaveStatus("idle")
      }
    },
    [clearTimers, isDirty, reportUnsaved, scheduleAutoSave],
  )

  // A draft this browser kept from an earlier session. Into an empty block it
  // simply goes back; over existing text the teacher decides — silently
  // overwriting either side would lose somebody's work.
  useEffect(() => {
    if (restored === null) return
    if (restored === contentRef.current) {
      clearDraft()
      return
    }
    if (isBlank(contentRef.current)) {
      setDraftOffer(null)
      applyContent(restored)
      return
    }
    setDraftOffer(restored)
  }, [restored, clearDraft, applyContent, isDirty])

  // Mount / unmount. The cleanup is where a collapsed block used to lose its
  // text: the debounce was cleared and nothing took its place. Now the
  // pending text is sent immediately and tracked in `inflightByBlock`, so
  // the parent's leave-page warning and a re-opened editor both know about it.
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      clearTimers()
      if (savingRef.current || !isDirty()) return
      const blockId = block.id
      const snapshot = contentRef.current
      const previous = inflightByBlock.get(blockId) ?? Promise.resolve(null)
      const promise: Promise<string | null> = previous
        .then(() => coursesService.updateBlock(blockId, { content: snapshot }))
        .then((updated) => {
          onSavedRef.current(updated)
          reportUnsaved(false)
          return snapshot
        })
        .catch(() => {
          // The draft hook flushed this text to localStorage on the same
          // unmount, so it is not gone — but the server does not have it,
          // and the teacher needs to hear that from somewhere other than a
          // status line that no longer exists. `unsaved` stays true.
          toast({
            title: tRef.current("blockEditor.text.saveAfterCloseFailed"),
            description: tRef.current("blockEditor.text.saveAfterCloseFailedHint"),
            variant: "destructive",
          })
          return null
        })
        .finally(() => {
          if (inflightByBlock.get(blockId) === promise) inflightByBlock.delete(blockId)
        })
      inflightByBlock.set(blockId, promise)
    }
  }, [block.id, clearTimers, isDirty, reportUnsaved])

  // Re-opened while the previous instance's save is still travelling: once it
  // lands, show what landed — unless the teacher has already typed over it.
  useEffect(() => {
    const previous = inflightByBlock.get(block.id)
    if (!previous) return
    void previous.then((saved) => {
      if (saved === null || !mountedRef.current || isDirty()) return
      savedRef.current = saved
      contentRef.current = saved
      setContent(saved)
    })
  }, [block.id, isDirty])

  // The tab going to the background is the moment to save, not the moment
  // to stop saving: that is the teacher switching to Word for the next
  // paragraph. And `pagehide` is the last chance to reach the server before
  // the page is gone — `keepalive` lets the request outlive it.
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState !== "hidden") return
      if (!isDirty() || savingRef.current) return
      clearTimers()
      void performSave()
    }
    const onPageHide = () => {
      if (!isDirty()) return
      void api
        .put(
          `/blocks/${block.id}`,
          { content: contentRef.current },
          { adapter: "fetch", fetchOptions: { keepalive: true } },
        )
        .catch(() => {
          // The page is leaving; the localStorage draft is the fallback —
          // and the only path for a body over 64 KB, which browsers refuse
          // to send with `keepalive` at all.
        })
    }
    document.addEventListener("visibilitychange", onVisibilityChange)
    window.addEventListener("pagehide", onPageHide)
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange)
      window.removeEventListener("pagehide", onPageHide)
    }
  }, [block.id, clearTimers, isDirty, performSave])

  const saveExplicit = async () => {
    clearTimers()
    setSavingExplicit(true)
    try {
      await performSave({ explicit: true })
    } finally {
      if (mountedRef.current) setSavingExplicit(false)
    }
  }

  const restoreDraft = () => {
    if (draftOffer === null) return
    const draft = draftOffer
    setDraftOffer(null)
    applyContent(draft)
  }

  const discardDraft = () => {
    setDraftOffer(null)
    clearDraft()
    reportUnsaved(isDirty())
  }

  return (
    <>
      {draftOffer !== null && (
        <div
          role="status"
          className="rounded-md border border-warning/40 bg-warning/15 px-3 py-2 text-sm text-ink"
        >
          <p className="flex items-start gap-2">
            <AlertTriangle
              className="mt-0.5 h-4 w-4 shrink-0 text-warning-ink"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <span>{t("blockEditor.text.draftFound")}</span>
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={restoreDraft}>
              {t("blockEditor.text.draftRestore")}
            </Button>
            <Button size="sm" variant="outline" onClick={discardDraft}>
              {t("blockEditor.text.draftDiscard")}
            </Button>
          </div>
        </div>
      )}
      <RichTextEditor
        content={content}
        onChange={applyContent}
        placeholder={t("blockEditor.text.placeholder")}
        // Mirrors ``ChapterBlock.content`` Pydantic ``max_length=500_000``.
        // The TipTap CharacterCount extension counts the plain-text
        // length (without HTML tags), but the backend cap is on the
        // HTML payload — keeping them equal is a comfortable
        // overestimate: with markup overhead the actual stored bytes
        // can exceed plain-text-length but stays well under typical
        // body-size limits.
        characterLimit={500000}
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
          <span className="text-xs text-ink-muted">
            {t("blockEditor.text.statusUnsaved")}
          </span>
        )}
        {autoSaveStatus === "saving" && (
          <span className="flex items-center gap-1 text-xs text-ink-muted">
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
        {autoSaveStatus === "failed" && (
          <span
            role="alert"
            className="flex items-center gap-1 text-xs text-destructive"
          >
            <AlertTriangle className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
            {t("blockEditor.text.statusFailed")}
          </span>
        )}
      </div>
    </>
  )
}
