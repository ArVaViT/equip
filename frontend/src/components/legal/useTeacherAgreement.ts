import { useCallback, useEffect, useRef, useState } from "react"
import { legalService, type LegalDocumentSummary } from "@/services/legal"

/** The document this hook exists for. */
export const TEACHER_TERMS = "teacher-terms"

/**
 * The same answer, reachable from a route guard.
 *
 * ``Gate`` in ``App.tsx`` decides during render whether to let somebody into
 * ``/teacher/*``, and it must refuse while the agreement is outstanding. It
 * cannot own the poll — it renders once per gated route and would start one
 * fetch loop per navigation — so the hook publishes what it learned and the
 * guard subscribes. Module-level for the same reason ``tourState`` is: there
 * is exactly one of each orchestrator in the tree, and a signal that flows
 * upward cannot be threaded through context from a child.
 */
let _teacherAgreementOwed = false
const owedListeners = new Set<() => void>()

export function getTeacherAgreementOwed(): boolean {
  return _teacherAgreementOwed
}

export function subscribeTeacherAgreement(cb: () => void): () => void {
  owedListeners.add(cb)
  return () => {
    owedListeners.delete(cb)
  }
}

function publishOwed(next: boolean): void {
  if (_teacherAgreementOwed === next) return
  _teacherAgreementOwed = next
  owedListeners.forEach((cb) => cb())
}

/**
 * How often to re-ask the server whether this person owes anything new.
 *
 * Five minutes, matching nothing in particular: the question is "has somebody
 * been made a teacher since this tab was opened", and the honest answer is
 * that nobody is waiting on it to the second. Cheap enough to poll at a scale
 * of tens of users, slow enough not to be a background load at any scale we
 * are near.
 */
const POLL_MS = 5 * 60 * 1000

/**
 * Whether this person still owes the Teacher & Contributor Agreement.
 *
 * Why this is a poll and not a read of ``user.role``: it cannot be a read of
 * ``user.role``. ``AuthContext`` fetches the profile once, when the signed-in
 * user id changes, and deliberately short-circuits the two events that would
 * otherwise refetch it — ``SIGNED_IN`` on tab focus and the hourly
 * ``TOKEN_REFRESHED`` — because the profile row barely changes. Which is true
 * except for the one field that makes somebody a teacher. An administrator
 * granting the role, a director sending an invitation somebody accepts on
 * another device: an open tab knows nothing about either until a full reload.
 *
 * The server does know. ``GET /legal/acceptances/me`` answers for the role on
 * the profile row, so the agreement appearing in ``outstanding`` *is* the
 * promotion arriving. Asking again on focus covers the common case — somebody
 * is told "you're a teacher now", switches back to the tab — and the interval
 * covers a tab that was never left.
 *
 * Its own request rather than a shared store with ``FirstRunFlow``: one more
 * call to a cheap endpoint on load, against a module-level cache that would
 * have to be reset between tests and between accounts. At this size the
 * request is the cheaper of the two.
 */
export function useTeacherAgreement(userId: string | undefined) {
  const [owed, setOwed] = useState<LegalDocumentSummary | null>(null)
  // Set the moment the person accepts, so the gate closes on the click rather
  // than on the next poll. The server is authoritative; this is the optimism
  // that keeps a confirmed action from feeling like a hung button.
  const [accepted, setAccepted] = useState(false)
  const lastCheck = useRef(0)

  const check = useCallback(() => {
    if (!userId) return
    lastCheck.current = Date.now()
    legalService.status().then(
      (status) => {
        const found = status.outstanding.find((doc) => doc.slug === TEACHER_TERMS) ?? null
        setOwed(found)
        publishOwed(found !== null)
      },
      () => {
        // A failed check must not become a gate nobody can pass. Leaving the
        // previous answer in place means a network blip does not throw a
        // congratulation screen at somebody mid-sentence, and does not close
        // one either.
      },
    )
  }, [userId])

  useEffect(() => {
    if (!userId) {
      setOwed(null)
      setAccepted(false)
      publishOwed(false)
      return
    }
    setAccepted(false)
    check()
    const interval = window.setInterval(check, POLL_MS)
    const onVisible = () => {
      // Throttled, or a person flicking between two tabs generates a request
      // per flick.
      if (document.visibilityState !== "visible") return
      if (Date.now() - lastCheck.current < 30_000) return
      check()
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      window.clearInterval(interval)
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [userId, check])

  return {
    /** The agreement, when it is owed and has not just been accepted. */
    owed: accepted ? null : owed,
    onAccepted: useCallback(() => {
      setAccepted(true)
      publishOwed(false)
    }, []),
  }
}
