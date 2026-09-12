/**
 * "Your list of courses just changed" — a one-line store the dashboard
 * can subscribe to.
 *
 * The dashboard fetches enrolled courses in an effect keyed on the user
 * id and the locale, which is correct for every case except the one
 * that matters most: accepting an invitation enrols the person while
 * they are already signed in, so neither key moves and the dashboard
 * keeps showing the empty state it loaded a minute ago. Reported from
 * the real thing — "when onboarding finished I was on the home page
 * with no courses, and refreshing showed the course".
 *
 * Deliberately not a data cache. It carries no enrollments, only the
 * fact that they changed; whoever cares re-reads from the server, which
 * keeps one source of truth and makes a stale render impossible.
 */

let version = 0
const listeners = new Set<() => void>()

/** Announce that this person's enrollments are no longer what was read. */
export function enrollmentsChanged(): void {
  version += 1
  for (const listener of listeners) listener()
}

export function subscribeEnrollments(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** For ``useSyncExternalStore``: changes exactly when the list does. */
export function enrollmentsVersion(): number {
  return version
}
