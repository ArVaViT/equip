import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { authService } from "@/services/auth"
import { supabase } from "@/lib/supabase"
import { completeAuthLanding, hasAuthArrival } from "@/lib/authLanding"
import AuthLayout from "@/components/layout/AuthLayout"
import { makeNewPasswordSchema } from "@/lib/validations/auth"
import { ExpiredLink } from "@/components/auth/ExpiredLink"
import { useAuth } from "@/context/useAuth"
import { PasswordFields } from "@/components/auth/PasswordFields"
import { usePasswordAffordances } from "@/components/auth/usePasswordAffordances"
import { Loader2, CheckCircle2 } from "lucide-react"
import { authErrorMessage } from "@/lib/authError"

export default function ResetPassword() {
  const { t } = useTranslation()
  const { resetPassword } = useAuth()
  const [form, setForm] = useState({ password: "" })
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({})
  const [serverError, setServerError] = useState("")
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const setPassword = useCallback((value: string) => {
    setForm({ password: value })
    setErrors({})
  }, [])
  const passwordAffordances = usePasswordAffordances(setPassword)
  const handlePasswordChange = useCallback(
    (value: string) => {
      passwordAffordances.noteEdited()
      setForm({ password: value })
      setErrors({})
    },
    [passwordAffordances],
  )
  const navigate = useNavigate()
  const redirectTimer = useRef<ReturnType<typeof setTimeout>>()
  // Changing a password needs the session the recovery link carries. Without
  // this the page showed the form to anybody who landed here, took a new
  // password, and answered with GoTrue's "Auth session missing" — which
  // tells a person nothing about the one thing that would help: asking for
  // a fresh link.
  const [linkState, setLinkState] = useState<"checking" | "ready" | "missing">("checking")

  useEffect(() => {
    return () => {
      if (redirectTimer.current) clearTimeout(redirectTimer.current)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!cancelled && session) setLinkState("ready")
    })
    let timer: ReturnType<typeof setTimeout> | undefined
    if (hasAuthArrival()) {
      // Arrived from the email: the link's token was taken out of the URL in
      // `main.tsx` and is verified here. Its answer is the answer — no timer,
      // a slow connection must not be told the link expired.
      void completeAuthLanding().then((result) => {
        if (!cancelled) setLinkState(result.status === "signed-in" ? "ready" : "missing")
      })
    } else {
      // Arrived some other way (a reload, or from the callback page, which
      // has already signed the person in): whatever session exists is it.
      timer = setTimeout(() => {
        if (!cancelled) setLinkState((prev) => (prev === "checking" ? "missing" : prev))
      }, 4000)
      void supabase.auth.getSession().then(({ data }) => {
        if (!cancelled && data.session) setLinkState("ready")
      })
    }
    return () => {
      cancelled = true
      clearTimeout(timer)
      subscription.unsubscribe()
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setServerError("")

    const result = makeNewPasswordSchema().safeParse(form)
    if (!result.success) {
      const fieldErrors: typeof errors = {}
      for (const issue of result.error.issues) {
        const key = String(issue.path[0])
        if (!fieldErrors[key]) fieldErrors[key] = issue.message
      }
      setErrors(fieldErrors)
      return
    }

    setLoading(true)
    try {
      await authService.updatePassword(result.data.password)
      setSuccess(true)
      redirectTimer.current = setTimeout(() => navigate("/", { replace: true }), 2500)
    } catch (err) {
      // Same rule as the sign-in screen: translate, and keep the server's
      // English for the dev console. This one has two outcomes worth
      // telling apart on their own — a password too weak to accept, and a
      // reset link that expired while the tab sat open — and the helper
      // reads GoTrue's `code` for both.
      setServerError(authErrorMessage(err, "auth.resetPassword.errors.resetFailed"))
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <AuthLayout heading={t("auth.resetPassword.successHeading")}>
        <div className="flex flex-col items-center text-center gap-4 py-6 animate-fade-in">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-success/10">
            <CheckCircle2 className="h-8 w-8 text-success-ink" strokeWidth={1.75} aria-hidden />
          </div>
          <p className="text-sm text-ink-muted">
            {t("auth.resetPassword.successBody")}
            <br />
            {t("auth.resetPassword.redirecting")}
          </p>
          <div className="h-1 w-24 rounded-full bg-muted overflow-hidden">
            <div className="animate-grow-bar h-full rounded-full bg-brand" />
          </div>
        </div>
      </AuthLayout>
    )
  }

  if (linkState !== "ready") {
    return (
      <AuthLayout heading={t("auth.resetPassword.heading")}>
        {linkState === "checking" ? (
          <div className="flex flex-col items-center gap-3 py-8">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand border-t-transparent" />
            <span className="text-sm text-ink-muted">{t("auth.callback.completing")}</span>
          </div>
        ) : (
          <ExpiredLink send={resetPassword} />
        )}
      </AuthLayout>
    )
  }

  return (
    <AuthLayout heading={t("auth.resetPassword.heading")}>
      <div className="space-y-6 animate-fade-in">
        {serverError && (
          <div role="alert" className="text-sm text-destructive-ink bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
            {serverError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <PasswordFields
            idPrefix="reset"
            label={t("auth.resetPassword.newPassword")}
            password={form.password}
            passwordError={errors.password}
            showPassword={passwordAffordances.showPassword}
            passwordGenerated={passwordAffordances.passwordGenerated}
            onChange={handlePasswordChange}
            onToggleShowPassword={passwordAffordances.toggleShowPassword}
            onGeneratePassword={passwordAffordances.generate}
          />

          <Button type="submit" size="lg" className="w-full font-medium" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
                {t("auth.resetPassword.submitting")}
              </>
            ) : (
              t("auth.resetPassword.submit")
            )}
          </Button>
        </form>
      </div>
    </AuthLayout>
  )
}
