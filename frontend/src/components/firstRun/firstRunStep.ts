import { firstRunCompletedKey, privacyAcceptedKey } from "@/lib/storageKeys"
import type { User } from "@/types"

export type Step = "privacy" | "name" | "picker" | "splash" | "done"

/** The slice of the profile the flow's decisions are made from. */
export type FirstRunUser = Pick<User, "id" | "role" | "full_name" | "onboarding_completed_at">

export function readFlag(key: string): boolean {
  if (typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(key) === "1"
  } catch {
    return false
  }
}

export function writeFlag(key: string): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(key, "1")
  } catch {
    /* private browsing — the gate will fire again next visit */
  }
}

export function clearFlag(key: string): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* private browsing — nothing was cached to begin with */
  }
}

/**
 * Whether this account has been through the first-run flow.
 *
 * The profile is the record; the browser flag is a cache of it. The cache is
 * consulted here in the *permissive* direction — a browser that finished the
 * flow before the server kept a record still passes — because for this
 * screen, unlike the consent gate, asking twice is the bug and asking never
 * costs nothing: a student with no courses lands on a dashboard that points
 * at the catalogue. ``FirstRunFlow`` reports a cache-only pass to the server,
 * so the next device does not need the cache.
 */
export function onboardingFinished(user: Pick<FirstRunUser, "id" | "onboarding_completed_at">): boolean {
  return Boolean(user.onboarding_completed_at) || readFlag(firstRunCompletedKey(user.id))
}

/**
 * Which step to show.
 *
 * The legal gate is decided by the server — `legalService.status()` says what
 * is still outstanding. The `localStorage` flag is a **cache**, not evidence:
 * without it the gate could only appear after a round-trip, which means the
 * dashboard flashes at somebody who has not agreed to anything; and its
 * absence is the safe direction to be wrong in, because being asked twice
 * costs a click while being asked never is the bug consent exists to prevent.
 * So: trust the cache until the server answers, then believe the server and
 * rewrite the cache.
 *
 * Whether the rest of the flow has been finished is decided the same way,
 * from `profiles.onboarding_completed_at` — see ``onboardingFinished``. Until
 * 2026-09 that mark lived only in this browser, so a second device, a private
 * window or cleared site data ran a returning student through account setup
 * and the course picker again. That was the owner's complaint, verbatim.
 *
 * What remains of the flow after consent: a name, asked only when the profile
 * has none (an email sign-up typed one; Google supplied one), and the course
 * picker, which is the one step that turns an empty dashboard into a course
 * to open. Only students see the picker — a teacher or director signing in
 * has a different first screen and nothing to enroll in.
 *
 * ``nameDeclined`` is session state: somebody who skipped the name step must
 * not be sent back to it when the legal status arrives a moment later.
 */
export function decideInitialStep(
  user: FirstRunUser | null | undefined,
  legalOutstanding: boolean | null,
  nameDeclined = false,
): Step {
  if (!user) return "done"
  const stillOwed = legalOutstanding ?? !readFlag(privacyAcceptedKey(user.id))
  if (stillOwed) return "privacy"
  if (onboardingFinished(user)) return "done"
  if (user.role !== "student") return "done"
  if (!nameDeclined && !(user.full_name ?? "").trim()) return "name"
  return "picker"
}
