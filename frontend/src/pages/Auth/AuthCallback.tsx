import { takeReturnPath } from "@/lib/authRedirect"
import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import AuthLayout from "@/components/layout/AuthLayout"
import { ExpiredLink } from "@/components/auth/ExpiredLink"
import { useAuth } from "@/context/useAuth"
import { supabase } from "@/lib/supabase"
import { completeAuthLanding, type AuthLandingResult } from "@/lib/authLanding"

/**
 * How long the link's verification may take before the page stops waiting.
 * supabase-js has no timeout of its own, and a `verifyOtp` that never
 * answered left «Completing sign-in…» spinning with no way out but the
 * address bar.
 */
export const AUTH_LANDING_TIMEOUT_MS = 30_000

/**
 * Where Google (`/auth/callback`) and every email link but recovery
 * (`/auth/confirm`) land. `main.tsx` has already taken the code or token out
 * of the URL; this page turns it into a session and moves on.
 *
 * A link that did not sign anyone in is not always a failure: opened a second
 * time in the browser it already signed in, it is spent — and the person is
 * signed in all the same. So a session already here is success, whatever the
 * link said. Only without one does the page say the link is spent, and then
 * it offers a new one on the spot instead of sending the person to a sign-in
 * page three seconds later.
 */
export default function AuthCallback() {
  const navigate = useNavigate()
  const handled = useRef(false)
  const [outcome, setOutcome] = useState<"working" | "expired" | "nothing">("working")
  const { sendSignInLink } = useAuth()
  const { t } = useTranslation()

  useEffect(() => {
    let cancelled = false

    const go = (path: string) => {
      if (handled.current) return
      handled.current = true
      navigate(path, { replace: true })
    }

    let timer: ReturnType<typeof setTimeout> | undefined
    const gaveUp = new Promise<AuthLandingResult>((resolve) => {
      timer = setTimeout(() => resolve({ status: "failed", reason: "other" }), AUTH_LANDING_TIMEOUT_MS)
    })
    void Promise.race([completeAuthLanding(), gaveUp]).then(async (result) => {
      clearTimeout(timer)
      if (cancelled) return
      if (result.status === "signed-in") {
        go(result.recovery ? "/auth/reset-password" : (takeReturnPath() ?? "/"))
        return
      }
      const { data } = await supabase.auth.getSession()
      if (cancelled) return
      if (data.session) {
        go(takeReturnPath() ?? "/")
        return
      }
      // A link that failed, or nothing in the URL at all (a reload after the
      // sign-in finished elsewhere, or Google cancelled).
      // An unfamiliar failure is not passed off as an expiry.
      setOutcome(result.status === "failed" && result.reason === "expired" ? "expired" : "nothing")
    })

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [navigate])

  if (outcome === "expired") {
    return (
      <AuthLayout heading={t("auth.signIn")}>
        <ExpiredLink send={sendSignInLink} />
      </AuthLayout>
    )
  }

  if (outcome === "nothing") {
    return (
      <AuthLayout heading={t("auth.welcomeBack")}>
        <div className="space-y-4 animate-fade-in">
          <p role="alert" className="text-sm text-ink">
            {t("auth.callback.timedOut")}
          </p>
          <Link to="/login" className="block">
            <Button size="lg" className="w-full">
              {t("auth.signIn")}
            </Button>
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand border-t-transparent" />
        <span className="text-sm text-ink-muted">{t("auth.callback.completing")}</span>
      </div>
    </div>
  )
}
