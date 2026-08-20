import { useState, useCallback, useEffect, useRef, useMemo } from "react"
import { supabase } from "@/lib/supabase"
import { authService } from "@/services/auth"
import { DEFAULT_LOCALE, isSupportedLocale, type SupportedLocale } from "@/i18n/config"
import type { User } from "@/types"
import { AuthContext } from "./auth-context"
import { setDatadogUser, clearDatadogUser } from "@/lib/datadog"
import { cacheClear } from "@/lib/cache"

// ``reconcileFreshOAuthLocale`` lived here previously — a silent
// post-signup PATCH that fired whenever ``profile.preferred_locale``
// was the column default "ru" within 60 s of account creation. It
// was designed for Google OAuth (no metadata), but the gate ("profile
// is ru AND browser locale differs") tripped indistinguishably for
// email signups whose user genuinely registered in ru while their
// browser was set to en. Result: silent override of the user's
// explicit registration choice. The FirstRunFlow's SetupStep is now
// the canonical first-run locale UX for ALL signup paths (OAuth and
// email alike), so the heuristic is gone.

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
function hasStoredSupabaseSession(): boolean {
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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  // Seed from the synchronous storage probe: anonymous visitors (no token)
  // skip the spinner and paint the public landing immediately; signed-in
  // visitors wait for profile enrichment as before.
  const [loading, setLoading] = useState(hasStoredSupabaseSession)
  const mounted = useRef(true)
  const activeUserId = useRef<string | null>(null)
  // ``inflightUserId`` deduplicates *simultaneous* enrichProfile() calls
  // for the same user. The activeUserId guards at the onAuthStateChange
  // callsites short-circuit *sequential* duplicates (SIGNED_IN after
  // INITIAL_SESSION), but they don't help when two events fire in the
  // same render tick — both setting activeUserId.current = uid before
  // either's supabase request lands. Production /rest/v1/profiles logs
  // showed duplicate GETs 2µs apart for every tab focus.
  const inflightUserId = useRef<string | null>(null)

  const enrichProfile = useCallback((userId: string, email: string) => {
    // Same userId already in flight — second caller piggybacks on the
    // first result (which will setUser + setLoading(false) once).
    if (inflightUserId.current === userId) return
    inflightUserId.current = userId
    activeUserId.current = userId
    // Supabase resolves with `{ data, error }` even for failures — it does NOT
    // reject the promise — so relying on the `.then` rejection handler only
    // would leave `loading` stuck forever on DB errors. Handle `error` in the
    // success branch explicitly.
    supabase
      .from("profiles")
      .select("*")
      .eq("id", userId)
      .single()
      .then(
        ({ data, error }) => {
          // Clear inflight regardless of outcome — a failed fetch
          // should still allow a fresh retry on the next tab focus.
          if (inflightUserId.current === userId) inflightUserId.current = null
          if (!mounted.current || activeUserId.current !== userId) return
          if (error || !data) {
            setLoading(false)
            return
          }
          const nextUser: User = {
            id: data.id,
            email: data.email || email,
            full_name: data.full_name,
            avatar_url: data.avatar_url ?? null,
            role: data.role,
            // Profile rows are CHECK-constrained to the supported locale
            // set, but defend against drift / older rows by validating with
            // `isSupportedLocale`. Fall back to `DEFAULT_LOCALE` — a value
            // this platform does not serve tells us nothing about the
            // reader, and the answer to knowing nothing is English, not a
            // locale that isn't actually theirs.
            preferred_locale: isSupportedLocale(data.preferred_locale)
              ? data.preferred_locale
              : DEFAULT_LOCALE,
            // "default" means the signup never carried a language and the
            // column just had to hold something — `useLocaleSync` then
            // keeps the browser's language instead of switching to a
            // preference nobody expressed. An older server that does not
            // send the field is read as "chosen", which is the safe
            // reading: never overwrite what might be a real preference.
            locale_source: data.locale_source ?? "chosen",
            created_at: data.created_at,
            updated_at: data.updated_at,
          }
          setUser(nextUser)
          // Attach the authenticated user to the current RUM session so
          // every downstream view/action/error/replay is tagged with
          // user.id / user.email / user.name / user.role.
          setDatadogUser({
            id: nextUser.id,
            email: nextUser.email,
            name: nextUser.full_name,
            role: nextUser.role,
          })
          setLoading(false)
        },
        () => {
          if (inflightUserId.current === userId) inflightUserId.current = null
          if (mounted.current && activeUserId.current === userId) {
            setLoading(false)
          }
        },
      )
  }, [])

  useEffect(() => {
    mounted.current = true

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (!mounted.current) return

        // We deliberately do NOT seed user state from ``userFromSupabase`` on
        // SIGNED_IN / INITIAL_SESSION: that value reads role from
        // ``user_metadata`` which is unreliable (often stale or missing, so
        // teachers/admins get demoted to student for one render). The
        // authoritative role lives in the ``profiles`` row that
        // ``enrichProfile`` loads.
        //
        // Supabase fires SIGNED_IN every tab focus and TOKEN_REFRESHED every
        // ~1h, both with the *same* user. Pre-fix we re-ran ``enrichProfile``
        // for every one of them, so the production /rest/v1/profiles logs
        // showed duplicate GETs in the same millisecond on every tab focus.
        // The profile row barely changes (full_name / avatar / role mutate
        // on admin action, not on JWT refresh), so we only re-fetch when
        // the user id actually changes — i.e. a real sign-in by a new
        // account. Same-user events become a no-op.
        if (event === "INITIAL_SESSION") {
          if (session?.user) {
            enrichProfile(session.user.id, session.user.email ?? "")
          } else {
            setLoading(false)
          }
          return
        }

        if (event === "SIGNED_IN" && session?.user) {
          if (activeUserId.current === session.user.id) {
            // Tab refocus or auto-refresh with the same account — we
            // already have the authoritative profile loaded.
            return
          }
          // A DIFFERENT account signed in (or the first account after an
          // anonymous session). The in-memory service cache may still hold
          // the previous user's (or the guest's) API payloads — clear it so
          // nothing bleeds across accounts on a shared device.
          cacheClear()
          setLoading(true)
          enrichProfile(session.user.id, session.user.email ?? "")
          return
        }

        if (event === "TOKEN_REFRESHED" && session?.user) {
          // Pure JWT refresh — no profile change implied. The
          // ``services/api.ts`` token cache picks the new JWT up on its
          // own ``onAuthStateChange`` subscription, so we don't need
          // to do anything here.
          if (activeUserId.current === session.user.id) return
          enrichProfile(session.user.id, session.user.email ?? "")
          return
        }

        if (event === "SIGNED_OUT") {
          activeUserId.current = null
          setUser(null)
          clearDatadogUser()
          // Drop the signed-out user's cached API payloads so the next
          // account on this device starts from a cold cache.
          cacheClear()
          setLoading(false)
        }
      },
    )

    return () => {
      mounted.current = false
      subscription.unsubscribe()
    }
  }, [enrichProfile])

  const login = useCallback(async (email: string, password: string) => {
    // Don't eagerly setUser from ``user_metadata`` — the SIGNED_IN event that
    // fires immediately after will load the authoritative profile.
    await authService.login(email, password)
  }, [])

  const register = useCallback(
    async (
      email: string,
      password: string,
      fullName: string,
      preferredLocale: SupportedLocale,
    ) => {
      await authService.register(email, password, fullName, preferredLocale)
    },
    [],
  )

  const signInWithGoogle = useCallback(async () => {
    await authService.signInWithGoogle()
  }, [])

  const resetPassword = useCallback(async (email: string) => {
    await authService.resetPassword(email)
  }, [])

  const refreshUser = useCallback(async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user) {
      if (mounted.current) setUser(null)
      return
    }
    enrichProfile(session.user.id, session.user.email ?? "")
  }, [enrichProfile])

  // See ``AuthContextValue.applyUser``. Same two guards ``enrichProfile``
  // applies to its own result: don't write after unmount, and don't write a
  // profile that belongs to a session we have already left.
  const applyUser = useCallback((next: User) => {
    if (!mounted.current) return
    if (activeUserId.current !== null && activeUserId.current !== next.id) return
    setUser(next)
  }, [])

  const logout = useCallback(async () => {
    try { await authService.logout() } catch { /* ignore */ }
    setUser(null)
    clearDatadogUser()
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, signInWithGoogle, resetPassword, logout, refreshUser, applyUser }),
    [user, loading, login, register, signInWithGoogle, resetPassword, logout, refreshUser, applyUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
