import { useCallback, useEffect, useRef, useState } from "react"
import { legalService, type LegalDocumentSummary } from "@/services/legal"

/** The document this hook exists for. */
export const TEACHER_TERMS = "teacher-terms"

/**
 * The other role-scoped document: a director binds the school with it.
 *
 * The consent gate on the server refuses every change from a director who has
 * not accepted it (``RUNS_A_SCHOOL`` in ``app/legal/registry.py``), and until
 * this screen asked for it nothing in the app did: the first-run flow takes
 * only what a student owes, and this gate took only the teacher terms. The one
 * director on the platform met a wall of 403s on grading — seventeen in a day,
 * under a toast telling him to accept documents he had already accepted.
 */
export const SCHOOL_AGREEMENT = "school-agreement"

/** In the order they are asked for: the agreement that makes somebody a
 *  teacher before the one that lets them bind a school. */
export const ROLE_DOCUMENTS = [TEACHER_TERMS, SCHOOL_AGREEMENT] as const
export type RoleDocument = (typeof ROLE_DOCUMENTS)[number]

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
/** A document at a version: a new version of the same document is a new thing to accept. */
const keyOf = (doc: LegalDocumentSummary) => `${doc.slug}@${doc.version}`

export function useTeacherAgreement(userId: string | undefined) {
  // Every role-scoped document the last answer listed, in the order they are
  // asked for. Kept whole so that accepting one shows the next at once,
  // without a round trip and without a moment in which nothing is owed — the
  // tour would read that moment as "the gate is gone" and start.
  const [owedList, setOwedList] = useState<LegalDocumentSummary[]>([])
  const owedListRef = useRef<LegalDocumentSummary[]>([])
  // Accepted in this tab, by slug and version. The gate closes on the click
  // rather than on the next poll, and no answer that left before the click can
  // bring an accepted document back. A set, because a director can owe two.
  const [accepted, setAccepted] = useState<ReadonlySet<string>>(() => new Set())
  const acceptedRef = useRef<ReadonlySet<string>>(new Set())
  // Only the newest request may answer. The poll, the focus check and the
  // check after an acceptance are unordered; a slow old answer must not
  // overwrite a newer one.
  const seq = useRef(0)
  const lastCheck = useRef(0)

  const stillOwed = (list: LegalDocumentSummary[], done: ReadonlySet<string>) =>
    list.some((doc) => !done.has(keyOf(doc)))

  const check = useCallback(() => {
    if (!userId) return
    lastCheck.current = Date.now()
    const mine = ++seq.current
    legalService.status().then(
      (status) => {
        if (mine !== seq.current) return
        const list = ROLE_DOCUMENTS.flatMap((slug) => status.outstanding.filter((doc) => doc.slug === slug))
        owedListRef.current = list
        setOwedList(list)
        publishOwed(stillOwed(list, acceptedRef.current))
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
    // A new person (or nobody) starts from nothing: no answer still in flight
    // for the previous one may land — after sign-out it would raise the gate
    // over the login page — and nothing they owed or accepted carries over.
    seq.current++
    const empty: ReadonlySet<string> = new Set()
    acceptedRef.current = empty
    setAccepted(empty)
    owedListRef.current = []
    setOwedList([])
    publishOwed(false)
    if (!userId) return
    check()
    // Not while the tab is hidden: coming back to it asks anyway (below), and a
    // forgotten background tab otherwise polls every five minutes all day —
    // this is already the endpoint real users call most (2026-10-03).
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") check()
    }, POLL_MS)
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
    /** The first document still owed and not accepted in this tab. */
    owed: owedList.find((doc) => !accepted.has(keyOf(doc))) ?? null,
    onAccepted: useCallback(
      (doc: LegalDocumentSummary) => {
        const next = new Set(acceptedRef.current).add(keyOf(doc))
        acceptedRef.current = next
        setAccepted(next)
        publishOwed(stillOwed(owedListRef.current, next))
        // Confirm with the server, and pick up anything that changed meanwhile.
        check()
      },
      [check],
    ),
  }
}
