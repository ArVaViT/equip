import { useCallback, useEffect, useRef, useState } from "react"

/**
 * Keeps unsent text alive across a reload.
 *
 * The case this exists for is specific and it is not hypothetical: a student
 * writes nine hundred words into a textarea over an hour, the phone drops the
 * tab out of memory or the browser reloads, and the work is gone. Nothing in
 * the product had ever written it anywhere. The submit button was the first
 * moment the text left the component.
 *
 * Deliberate choices:
 *
 * - **`localStorage`, not the server.** A server draft is the better feature
 *   and a much bigger one — it needs an endpoint, a conflict story between two
 *   devices, and a rule about what a teacher can see. This costs nothing and
 *   removes the loss. The two are not alternatives; this is the floor.
 * - **Debounced.** Writing on every keystroke is a synchronous serialisation
 *   on the main thread while somebody is typing.
 * - **Nothing is written until something was typed.** The value at mount is
 *   what the server (or the parent) already has; writing it would overwrite
 *   the one thing in storage that might be newer — the draft a crashed tab
 *   left behind, which the caller has not yet had the chance to offer back.
 * - **Flushed on the way out.** The debounce has a window, and the window is
 *   exactly when the loss happens: the last paste lands, the tab is closed or
 *   the component is swapped out half a second later, and the timer that was
 *   going to write it is cleared instead. Unmount and `pagehide` write the
 *   latest value synchronously — `localStorage` is one of the few things
 *   that still works in those last milliseconds.
 * - **Silent on failure.** Private mode, a full quota, a locked-down profile:
 *   every one of those throws, and none of them is a reason to interrupt
 *   somebody writing an essay. A draft that quietly does not save leaves the
 *   student exactly where they were before this existed.
 * - **Restore only into an empty field** by default, so a saved draft can
 *   never overwrite something newer that is already on screen. A caller that
 *   edits *existing* content (a teacher's text block already holds the lesson
 *   the draft extends) opts into `restoreInto: "any"` and receives the draft
 *   whenever it differs from what was on screen at mount — and then owns the
 *   decision of what to do with it. The hook never applies it by itself.
 */
export function useLocalDraft(
  key: string | null,
  value: string,
  {
    delay = 500,
    restoreInto = "empty",
  }: { delay?: number; restoreInto?: "empty" | "any" } = {},
): { restored: string | null; savedAt: number | null; clear: () => void } {
  const [restored, setRestored] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  // The value at mount decides whether restoring is safe, and it must not be a
  // dependency of the restore effect — the field changes the moment we restore.
  const initial = useRef(value)
  const latest = useRef(value)
  useEffect(() => {
    latest.current = value
  })
  // Set the first time the value moves away from what it was at mount. Until
  // then there is nothing of the user's to write, and plenty to overwrite.
  const touched = useRef(false)
  // What `clear()` was asked to forget. Neither the debounce nor the flush on
  // unmount may put a just-submitted essay straight back into storage.
  const cleared = useRef<string | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    if (!key) return
    if (restoreInto === "empty" && initial.current) return
    try {
      const stored = window.localStorage.getItem(key)
      if (stored && stored !== initial.current) setRestored(stored)
    } catch {
      // No storage available. Nothing to restore, nothing to say about it.
    }
  }, [key, restoreInto])

  const persist = useCallback(
    (next: string) => {
      if (!key) return
      try {
        if (next) {
          window.localStorage.setItem(key, next)
          setSavedAt(Date.now())
        } else {
          window.localStorage.removeItem(key)
          setSavedAt(null)
        }
      } catch {
        // See above: a draft that cannot be saved is not worth a dialog.
      }
    },
    [key],
  )

  useEffect(() => {
    if (!key) return
    if (value !== initial.current) touched.current = true
    if (!touched.current) return
    if (cleared.current !== null && value !== cleared.current) cleared.current = null
    if (value === cleared.current) return
    timer.current = window.setTimeout(() => {
      timer.current = null
      persist(value)
    }, delay)
    return () => {
      if (timer.current !== null) {
        window.clearTimeout(timer.current)
        timer.current = null
      }
    }
  }, [key, value, delay, persist])

  useEffect(() => {
    if (!key) return
    const flush = () => {
      if (!touched.current) return
      if (latest.current === cleared.current) return
      persist(latest.current)
    }
    window.addEventListener("pagehide", flush)
    return () => {
      window.removeEventListener("pagehide", flush)
      flush()
    }
  }, [key, persist])

  const clear = useCallback(() => {
    setRestored(null)
    setSavedAt(null)
    cleared.current = latest.current
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
    if (!key) return
    try {
      window.localStorage.removeItem(key)
    } catch {
      /* nothing to clear if there is no storage */
    }
  }, [key])

  return { restored, savedAt, clear }
}
