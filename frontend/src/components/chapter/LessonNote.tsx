import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { NotebookPen } from "lucide-react"

import { Textarea } from "@/components/ui/textarea"
import { NOTE_MAX_LENGTH, notesService } from "@/services/notes"

type SaveState = "idle" | "saving" | "saved" | "failed"

const SAVE_AFTER_MS = 1200

/**
 * The reader's own note on this lesson — the margin of their Bible, beside
 * the text it belongs to.
 *
 * Saves itself a moment after typing stops, and again when the box loses
 * focus, so nothing is lost to a closed tab; says so quietly. Collapsed to
 * one line until opened, unless there is a note already.
 */
export function LessonNote({ chapterId }: { chapterId: string }) {
  const { t } = useTranslation()
  const [body, setBody] = useState("")
  const [loaded, setLoaded] = useState(false)
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<SaveState>("idle")
  // Focus goes to the box only when the reader opened it themselves.
  const [openedByReader, setOpenedByReader] = useState(false)
  const saved = useRef("")
  const latest = useRef("")
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let live = true
    setLoaded(false)
    notesService
      .get(chapterId)
      .then((note) => {
        if (!live) return
        saved.current = note.body ?? ""
        latest.current = note.body ?? ""
        setBody(note.body ?? "")
        setOpen(Boolean(note.body))
      })
      .catch(() => undefined)
      .finally(() => live && setLoaded(true))
    return () => {
      live = false
    }
  }, [chapterId])

  const save = async (text: string) => {
    if (timer.current) clearTimeout(timer.current)
    if (text.trim() === saved.current.trim()) return
    setState("saving")
    try {
      const note = await notesService.save(chapterId, text)
      saved.current = note.body ?? ""
      setState("saved")
    } catch {
      setState("failed")
    }
  }

  const change = (text: string) => {
    setBody(text)
    latest.current = text
    setState("idle")
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => void save(text), SAVE_AFTER_MS)
  }

  // Whatever was typed and not yet saved goes when the lesson is left —
  // next lesson, back button — not only when the timer fires.
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
      if (latest.current.trim() !== saved.current.trim()) {
        void notesService.save(chapterId, latest.current).catch(() => undefined)
      }
    },
    [chapterId],
  )

  if (!loaded) return null

  return (
    <section aria-labelledby="lesson-note-heading" className="mb-8 rounded-md border border-edge p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 id="lesson-note-heading" className="flex items-center gap-2 text-sm font-medium">
          <NotebookPen className="h-4 w-4 text-ink-muted" strokeWidth={1.75} aria-hidden />
          {open ? (
            t("notes.lesson.title")
          ) : (
            <button
              type="button"
              onClick={() => {
                setOpen(true)
                setOpenedByReader(true)
              }} className="underline-offset-4 hover:underline">
              {t("notes.lesson.add")}
            </button>
          )}
        </h2>
        <Link to="/notes" className="text-xs text-ink-muted underline-offset-4 hover:text-ink hover:underline">
          {t("notes.lesson.all")}
        </Link>
      </div>
      {open && (
        <div className="mt-3 space-y-1">
          <Textarea
            value={body}
            onChange={(e) => change(e.target.value)}
            onBlur={() => void save(body)}
            maxLength={NOTE_MAX_LENGTH}
            aria-labelledby="lesson-note-heading"
            aria-describedby="lesson-note-state"
            placeholder={t("notes.lesson.placeholder")}
            className="min-h-[120px]"
            autoFocus={openedByReader}
          />
          <p id="lesson-note-state" className="text-xs text-ink-muted" aria-live="polite">
            {state === "saving"
              ? t("notes.lesson.saving")
              : state === "saved"
                ? t("notes.lesson.saved")
                : state === "failed"
                  ? t("notes.lesson.failed")
                  : t("notes.lesson.private")}
          </p>
        </div>
      )}
    </section>
  )
}
