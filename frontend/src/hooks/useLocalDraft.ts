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
 * - **Silent on failure.** Private mode, a full quota, a locked-down profile:
 *   every one of those throws, and none of them is a reason to interrupt
 *   somebody writing an essay. A draft that quietly does not save leaves the
 *   student exactly where they were before this existed.
 * - **Restore only into an empty field**, so a saved draft can never overwrite
 *   something newer that is already on screen.
 */
export function useLocalDraft(
  key: string | null,
  value: string,
  { delay = 500 }: { delay?: number } = {},
): { restored: string | null; savedAt: number | null; clear: () => void } {
  const [restored, setRestored] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  // The value at mount decides whether restoring is safe, and it must not be a
  // dependency of the restore effect — the field changes the moment we restore.
  const initial = useRef(value)

  useEffect(() => {
    if (!key || initial.current) return
    try {
      const stored = window.localStorage.getItem(key)
      if (stored) setRestored(stored)
    } catch {
      // No storage available. Nothing to restore, nothing to say about it.
    }
  }, [key])

  useEffect(() => {
    if (!key) return
    const id = window.setTimeout(() => {
      try {
        if (value) {
          window.localStorage.setItem(key, value)
          setSavedAt(Date.now())
        } else {
          window.localStorage.removeItem(key)
          setSavedAt(null)
        }
      } catch {
        // See above: a draft that cannot be saved is not worth a dialog.
      }
    }, delay)
    return () => window.clearTimeout(id)
  }, [key, value, delay])

  const clear = useCallback(() => {
    setRestored(null)
    setSavedAt(null)
    if (!key) return
    try {
      window.localStorage.removeItem(key)
    } catch {
      /* nothing to clear if there is no storage */
    }
  }, [key])

  return { restored, savedAt, clear }
}
