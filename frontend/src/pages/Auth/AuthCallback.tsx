import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { supabase } from "@/lib/supabase"

/**
 * Reads the failure GoTrue reports in the URL fragment.
 *
 * `/auth/v1/verify` answers a 303 to `redirect_to`, and when the token is
 * spent or stale it puts the reason in the fragment rather than refusing the
 * redirect: `#error=access_denied&error_code=otp_expired&…`. Without this,
 * such an arrival looked exactly like a slow OAuth round-trip — a spinner
 * for fifteen seconds and then "could not complete sign-in", which tells a
 * person nothing about the one thing they can act on: asking for a new link.
 */
function linkFailureFromHash(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""))
  const code = params.get("error_code")
  const error = params.get("error")
  if (!code && !error) return null
  // `otp_expired` covers both halves of what a person experiences as "the
  // link stopped working": genuinely past its lifetime, and already used.
  if (code === "otp_expired" || error === "access_denied") return "auth.errors.linkExpired"
  return "auth.callback.timedOut"
}

export default function AuthCallback() {
  const navigate = useNavigate()
  const handled = useRef(false)
  const [timedOut, setTimedOut] = useState(false)
  const [linkErrorKey, setLinkErrorKey] = useState<string | null>(null)
  const { t } = useTranslation()

  useEffect(() => {
    // Checked before the listener is armed: a failed verification never
    // produces a session, so waiting for one is waiting for nothing.
    const failure = linkFailureFromHash(window.location.hash)
    if (failure) {
      setLinkErrorKey(failure)
      return
    }

    let redirectTimer: ReturnType<typeof setTimeout> | undefined

    const go = (path: string) => {
      if (handled.current) return
      handled.current = true
      navigate(path, { replace: true })
    }

    const timeout = setTimeout(() => {
      setTimedOut(true)
      redirectTimer = setTimeout(() => go("/login?error=oauth_timeout"), 3000)
    }, 15000)

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (event === "PASSWORD_RECOVERY") {
          clearTimeout(timeout)
          go("/auth/reset-password")
        } else if (session) {
          clearTimeout(timeout)
          go("/")
        }
      },
    )

    return () => {
      clearTimeout(timeout)
      clearTimeout(redirectTimer)
      subscription.unsubscribe()
    }
  }, [navigate])

  if (linkErrorKey) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-3 px-6 text-center">
          <div className="h-8 w-8 rounded-full bg-destructive/10 flex items-center justify-center">
            <span className="text-destructive-ink text-lg font-bold">!</span>
          </div>
          <p role="alert" className="text-sm font-medium text-destructive-ink">
            {t(linkErrorKey)}
          </p>
          <Link to="/login" className="text-sm text-brand font-medium hover:text-brand-ink">
            {t("auth.signIn")}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="flex flex-col items-center gap-3">
        {timedOut ? (
          <>
            <div className="h-8 w-8 rounded-full bg-destructive/10 flex items-center justify-center">
              <span className="text-destructive-ink text-lg font-bold">!</span>
            </div>
            <span className="text-sm text-destructive font-medium">{t("auth.callback.timedOut")}</span>
            <span className="text-xs text-ink-muted">{t("auth.callback.redirecting")}</span>
          </>
        ) : (
          <>
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand border-t-transparent" />
            <span className="text-sm text-ink-muted">{t("auth.callback.completing")}</span>
          </>
        )}
      </div>
    </div>
  )
}
