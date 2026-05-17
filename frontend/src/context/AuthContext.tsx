import { useState, useCallback, useEffect, useRef, useMemo } from "react"
import i18n from "i18next"
import { supabase } from "@/lib/supabase"
import { authService } from "@/services/auth"
import { preferencesService } from "@/services/preferences"
import { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import type { User } from "@/types"
import { AuthContext } from "./auth-context"
import { setDatadogUser, clearDatadogUser } from "@/lib/datadog"

/**
 * Heuristic for "this profile was created by *this* signup, just now".
 * The window is generous on purpose: clock skew between the browser
 * and Supabase, plus the delay between trigger insert and the time
 * the AuthContext finally observes the row, can both be a few seconds.
 * 60s comfortably covers both without falsely flagging a returning
 * user whose profile happens to be a minute old.
 */
const FRESH_PROFILE_WINDOW_MS = 60_000

/**
 * Same Russian-or-English fold used by ``resolveDateLocale`` and the
 * register form. Anything else degrades silently and we make no PATCH.
 */
function browserPreferredLocale(): "ru" | "en" | null {
  const candidate = (i18n.resolvedLanguage ?? i18n.language ?? "").toLowerCase()
  if (candidate.startsWith("ru")) return "ru"
  if (candidate.startsWith("en")) return "en"
  return null
}

/**
 * For accounts created within the last minute whose profile locale
 * still matches the column default ('ru') but the browser is showing
 * a different supported language, PATCH the profile so the user keeps
 * the language they registered in.
 *
 * Specifically targets Google-OAuth signups, which can't ship
 * ``options.data.preferred_locale`` upfront the way email signup
 * can. Email signups never trip this — the trigger already wrote the
 * right value, so the guard sees a match and no-ops.
 */
async function reconcileFreshOAuthLocale(profile: User): Promise<User> {
  if (!profile.created_at) return profile
  if (profile.preferred_locale !== "ru") return profile

  const createdAtMs = new Date(profile.created_at).getTime()
  if (Number.isNaN(createdAtMs)) return profile
  if (Date.now() - createdAtMs > FRESH_PROFILE_WINDOW_MS) return profile

  const desired = browserPreferredLocale()
  if (!desired || desired === profile.preferred_locale) return profile

  try {
    return await preferencesService.setPreferredLocale(desired)
  } catch {
    // Non-fatal: a transient PATCH failure shouldn't break the post-
    // signup redirect. The user can flip the switcher manually and
    // we'll try again on the next refresh.
    return profile
  }
}

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
          // Fire-and-forget locale reconciliation for fresh accounts —
          // the result feeds back into the same state setter so
          // downstream listeners (``useLocaleSync``) pick up the new
          // value on the next render tick.
          void reconcileFreshOAuthLocale(nextUser).then((updated) => {
            if (!mounted.current || activeUserId.current !== userId) return
            if (updated !== nextUser) setUser(updated)
          })
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
        // ``enrichProfile`` loads. Tab refocus triggers SIGNED_IN with the
        // same user — if we already have them loaded we refresh silently
        // without toggling ``loading``, which avoids both a spinner flash
        // and a brief <Gate> redirect to "/".
        if (event === "INITIAL_SESSION") {
          if (session?.user) {
            enrichProfile(session.user.id, session.user.email ?? "")
          } else {
            setLoading(false)
          }
          return
        }

        if (event === "SIGNED_IN" && session?.user) {
          if (activeUserId.current !== session.user.id) {
            setLoading(true)
          }
          enrichProfile(session.user.id, session.user.email ?? "")
          return
        }

        if (event === "TOKEN_REFRESHED" && session?.user) {
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
