import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { supabase } from "@/lib/supabase"
import { completeAuthLanding, type AuthLandingResult } from "@/lib/authLanding"

/**
 * The failure to show for a link that did not sign anyone in.
 *
 * GoTrue does not refuse a spent or stale token outright — it redirects with
 * the reason (`error_code=otp_expired`), and `verifyOtp` answers with the
 * same code. Without naming it, such an arrival looked exactly like a slow
 * OAuth round-trip: a spinner and then "could not complete sign-in", which
 * tells a person nothing about the one thing they can act on — asking for a
 * new link.
 */
function failureKey(result: Extract<AuthLandingResult, { status: "failed" }>): string {
  return result.reason === "expired" ? "auth.errors.linkExpired" : "auth.callback.timedOut"
}

/**
 * Where Google (`/auth/callback`) and every email link but recovery
 * (`/auth/confirm`) land. `main.tsx` has already taken the code or token out
 * of the URL; this page turns it into a session and moves on.
 */
export default function AuthCallback() {
  const navigate = useNavigate()
  const handled = useRef(false)
  const [timedOut, setTimedOut] = useState(false)
  const [linkErrorKey, setLinkErrorKey] = useState<string | null>(null)
  const { t } = useTranslation()

  useEffect(() => {
    let cancelled = false
    let redirectTimer: ReturnType<typeof setTimeout> | undefined

    const go = (path: string) => {
      if (handled.current) return
      handled.current = true
      navigate(path, { replace: true })
    }

    void completeAuthLanding().then(async (result) => {
      if (cancelled) return
      if (result.status === "signed-in") {
        go(result.recovery ? "/auth/reset-password" : "/")
        return
      }
      if (result.status === "failed") {
        setLinkErrorKey(failureKey(result))
        return
      }
      // Nothing in the URL: a reload after the sign-in finished, or a visit
      // by hand. A session already here is the success; otherwise there is
      // nothing to wait for.
      const { data } = await supabase.auth.getSession()
      if (cancelled) return
      if (data.session) {
        go("/")
        return
      }
      setTimedOut(true)
      redirectTimer = setTimeout(() => go("/login?error=oauth_timeout"), 3000)
    })

    return () => {
      cancelled = true
      clearTimeout(redirectTimer)
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
