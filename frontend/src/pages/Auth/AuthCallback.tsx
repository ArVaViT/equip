import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { supabase } from "@/lib/supabase"

export default function AuthCallback() {
  const navigate = useNavigate()
  const handled = useRef(false)
  const [timedOut, setTimedOut] = useState(false)
  const { t } = useTranslation()

  useEffect(() => {
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

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="flex flex-col items-center gap-3">
        {timedOut ? (
          <>
            <div className="h-8 w-8 rounded-full bg-destructive/10 flex items-center justify-center">
              <span className="text-destructive text-lg font-bold">!</span>
            </div>
            <span className="text-sm text-destructive font-medium">{t("auth.callback.timedOut")}</span>
            <span className="text-xs text-muted-foreground">{t("auth.callback.redirecting")}</span>
          </>
        ) : (
          <>
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            <span className="text-sm text-muted-foreground">{t("auth.callback.completing")}</span>
          </>
        )}
      </div>
    </div>
  )
}
