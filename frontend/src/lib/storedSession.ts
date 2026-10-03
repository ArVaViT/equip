/**
 * Synchronous "is anyone plausibly signed in?" probe used to seed the initial
 * loading state. supabase-js persists its session under a
 * `sb-<project-ref>-auth-token` localStorage key; if no such key holds a value,
 * the visitor is definitely anonymous and we can render the public shell
 * immediately instead of blocking the whole app on the async
 * `INITIAL_SESSION` round-trip (the #1 cause of the >4s LCP on the landing).
 * A stored session still starts `loading=true` so a logged-in user never
 * flashes the anonymous landing before their dashboard. A localStorage that's
 * blocked or empty → treated as anonymous (paint now). Worst case for a stale/
 * expired stored token is the pre-existing behaviour: a brief spinner until
 * `INITIAL_SESSION` resolves it to signed-out.
 */
export function hasStoredSupabaseSession(): boolean {
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith("sb-") && k.endsWith("-auth-token")) {
        const v = localStorage.getItem(k)
        if (v && v !== "null") return true
      }
    }
  } catch {
    /* localStorage unavailable (private mode / blocked) → assume anonymous */
  }
  return false
}
