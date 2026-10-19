import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { NotebookPen } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useAuth } from "@/context/useAuth"
import { noteDraftKey } from "@/lib/storageKeys"
import { NOTE_MAX_LENGTH, notesService } from "@/services/notes"

type SaveState = "idle" | "saving" | "saved" | "failed"

/**
 * What this browser keeps of a note the server does not hold yet: the text
 * as typed, and the text it was typed over (`base`). On the next visit the
 * draft is sent only while the server still holds `base` — a note edited
 * on another device since then is kept, not written over.
 */
type NoteDraft = { text: string; base: string }

const SAVE_AFTER_MS = 1200

/**
 * The reader's own note on this lesson — the margin of their Bible, beside
 * the text it belongs to.
 *
 * Saves itself a moment after typing stops, on blur, and when the lesson is
 * left, so nothing is lost to a closed tab; says so quietly. Collapsed to one
 * line until opened, unless there is a note already.
 *
 * Rendered with `key={chapterId}` by the lesson page: a different lesson is a
 * different note, never this one's state carried over. Saves are handed to
 * `notesService`, which runs a lesson's saves one after another across
 * components and makes reads wait for them — so coming straight back to the
 * lesson reads what leaving it saved. A save of text already handed over is
 * skipped, so a blur and leaving never send the same note twice. Until the
 * note has loaded the box is not offered at all — typing into an empty box
 * over a note that failed to load would replace it.
 *
 * What is typed is also kept in this browser until the server confirms it.
 * The save sent on leaving the lesson has no screen to report to, and when
 * it was refused the note was gone; now the lesson's next visit finds the
 * draft, puts it back in the box and sends it again. Not `useLocalDraft`:
 * that hook counts any change from the value at mount as typing, and here
 * the note itself arrives after mount — it would have kept every loaded
 * note as a «draft» and, on a later visit, written it over an edit made on
 * another device.
 */
export function LessonNote({ chapterId }: { chapterId: string }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [body, setBody] = useState("")
  const [loaded, setLoaded] = useState<"pending" | "ok" | "failed">("pending")
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<SaveState>("idle")
  // Focus goes to the box only when the reader opened it themselves.
  const [openedByReader, setOpenedByReader] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const saved = useRef("")
  const latest = useRef("")
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // The text last handed to the service, landed or not.
  const sent = useRef("")
  const mounted = useRef(true)
  const draftKey = user ? noteDraftKey(user.id, chapterId) : null

  /**
   * The text as last typed here, kept while the server does not hold it —
   * together with the text it was typed over, so the next visit can tell
   * whether the server still holds that text or an edit made elsewhere.
   */
  const keepDraft = (text: string) => {
    if (!draftKey) return
    try {
      if (text.trim() === saved.current.trim()) window.localStorage.removeItem(draftKey)
      else window.localStorage.setItem(draftKey, JSON.stringify({ text, base: saved.current } satisfies NoteDraft))
    } catch {
      // No storage: the note is exactly as safe as it was before.
    }
  }

  /** The draft this browser kept for the lesson, or `null`. */
  const readDraft = (): NoteDraft | null => {
    if (!draftKey) return null
    try {
      const raw = window.localStorage.getItem(draftKey)
      if (raw === null) return null
      const parsed: unknown = JSON.parse(raw)
      if (
        parsed &&
        typeof parsed === "object" &&
        typeof (parsed as NoteDraft).text === "string" &&
        typeof (parsed as NoteDraft).base === "string"
      ) {
        return parsed as NoteDraft
      }
      window.localStorage.removeItem(draftKey)
      return null
    } catch {
      /* no storage, or not a draft: no draft */
      return null
    }
  }

  useEffect(() => {
    mounted.current = true
    let live = true
    notesService
      .get(chapterId)
      .then((note) => {
        if (!live) return
        const server = note.body ?? ""
        saved.current = server
        sent.current = server
        latest.current = server
        setBody(server)
        setOpen(Boolean(server))
        setLoaded("ok")
        // A draft this browser kept and the server never confirmed: the
        // note as it was last typed here. It goes back into the box and out
        // to the server — what leaving the lesson tried to do.
        const draft = readDraft()
        if (draft === null) return
        if (draft.text.trim() === server.trim()) {
          keepDraft(server)
          return
        }
        if (draft.base.trim() !== server.trim()) {
          // The note was edited elsewhere since this draft was typed — the
          // server holds a text the draft never saw. Sent anyway, the draft
          // would have written over that edit; the edit that was saved wins
          // over the one that was not.
          keepDraft(server)
          return
        }
        latest.current = draft.text
        setBody(draft.text)
        setOpen(true)
        timer.current = setTimeout(save, SAVE_AFTER_MS)
      })
      .catch(() => live && setLoaded("failed"))
    return () => {
      live = false
    }
    // `save` and `keepDraft` read refs only; the load belongs to the lesson.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterId, attempt])

  /** Hand the latest text to the service, unless it was handed over already. */
  const save = () => {
    if (timer.current) clearTimeout(timer.current)
    const text = latest.current
    if (text.trim() === sent.current.trim()) return
    sent.current = text
    if (mounted.current) setState("saving")
    notesService.save(chapterId, text).then(
      (note) => {
        saved.current = note.body ?? ""
        // Only what the server holds may be forgotten: a keystroke since
        // then is a newer draft, and the next save carries it.
        keepDraft(latest.current)
        if (mounted.current) setState(latest.current.trim() === saved.current.trim() ? "saved" : "idle")
      },
      () => {
        // Not saved: the next blur or keystroke tries again — and, after
        // the lesson was left, the draft kept in this browser does.
        sent.current = saved.current
        if (mounted.current) setState("failed")
      },
    )
  }

  const change = (text: string) => {
    setBody(text)
    latest.current = text
    setState("idle")
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      keepDraft(latest.current)
      save()
    }, SAVE_AFTER_MS)
  }

  // Whatever was typed and not yet saved goes when the lesson is left — to
  // the server, and to this browser in case the server says no. `pagehide`
  // is the tab closing inside the typing window, when no cleanup runs.
  useEffect(() => {
    const flush = () => keepDraft(latest.current)
    window.addEventListener("pagehide", flush)
    return () => {
      window.removeEventListener("pagehide", flush)
      mounted.current = false
      if (timer.current) clearTimeout(timer.current)
      flush()
      save()
    }
    // `save` and `keepDraft` read refs only; the cleanup must run once, on leaving.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (loaded === "pending") return null

  if (loaded === "failed") {
    return (
      <section className="mb-8 flex flex-wrap items-center justify-between gap-2 rounded-md border border-edge p-4 text-sm">
        <span className="flex items-center gap-2 text-ink-muted">
          <NotebookPen className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("notes.lesson.loadFailed")}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setLoaded("pending")
            setAttempt((n) => n + 1)
          }}
        >
          {t("common.tryAgain")}
        </Button>
      </section>
    )
  }

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
              }}
              className="underline-offset-4 hover:underline"
            >
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
            onBlur={save}
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
