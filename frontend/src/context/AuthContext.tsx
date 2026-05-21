import { useState, useCallback, useEffect, useRef, useMemo } from "react"
import { supabase } from "@/lib/supabase"
import { authService } from "@/services/auth"
import { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import type { User } from "@/types"
import { AuthContext } from "./auth-context"
import { setDatadogUser, clearDatadogUser } from "@/lib/datadog"

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const mounted = useRef(true)
  const activeUserId = useRef<string | null>(null)

  const enrichProfile = useCallback((userId: string, email: string) => {
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
            // `isSupportedLocale`. Fall back to `DEFAULT_LOCALE` ("ru") since
            // that's the project's source language and every existing course
            // is authored in it — this keeps unknown values from silently
            // pinning users to a locale that isn't actually theirs.
            preferred_locale: isSupportedLocale(data.preferred_locale)
              ? data.preferred_locale
              : DEFAULT_LOCALE,
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
      role: "teacher" | "student",
      preferredLocale: "en" | "ru",
    ) => {
      await authService.register(email, password, fullName, role, preferredLocale)
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

  const logout = useCallback(async () => {
    try { await authService.logout() } catch { /* ignore */ }
    setUser(null)
    clearDatadogUser()
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, signInWithGoogle, resetPassword, logout, refreshUser }),
    [user, loading, login, register, signInWithGoogle, resetPassword, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
