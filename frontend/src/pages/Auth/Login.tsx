import { useCallback, useEffect, useState } from "react"
import { Link, useLocation, useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/useAuth"
import { makeLoginSchema, type LoginFormData } from "@/lib/validations/auth"
import AuthLayout from "@/components/layout/AuthLayout"
import { Loader2, RefreshCw } from "lucide-react"
import { authErrorMessage, isEmailNotConfirmed, isRateLimited } from "@/lib/authError"
import { GoogleButton, OrDivider } from "@/components/auth/GoogleButton"
import { authService } from "@/services/auth"
import { useCooldown } from "@/hooks/useCooldown"
import { SignInLinkSent } from "./SignInLinkSent"
import { takeSignOutReason, type SignOutReason } from "@/lib/signOutReason"
import { emailFromState, peekReturnPath, rememberReturnPath, returnPathFrom } from "@/lib/authRedirect"

/**
 * Why the sign-in form is on screen, when the person did not come here on
 * purpose. Four arrivals used to look identical — a blank form:
 *
 * - the session expired mid-work and `api.ts` signed the person out;
 * - the server reported the account deactivated;
 * - the person deleted their own account, or asked to restore it from a
 *   session older than the deletion;
 * - `/auth/confirm` waited fifteen seconds for a session that never came and
 *   sent them here with `?error=oauth_timeout`, which nothing read;
 * - `Gate` refused a private page to a guest.
 *
 * Returns a key, not a sentence: resolved at render, so a language switch
 * re-translates it.
 */
function noticeKeyFor(error: string | null, reason: SignOutReason | null, state: unknown): string | null {
  if (reason === "session_expired") return "auth.notice.sessionExpired"
  if (reason === "account_deactivated") return "auth.notice.accountDeactivated"
  if (reason === "account_deleted") return "auth.notice.accountDeleted"
  if (reason === "restore_needs_sign_in") return "auth.notice.restoreNeedsSignIn"
  if (error === "oauth_timeout") return "auth.callback.timedOut"
  // The same target the public gate will use after sign-in, so the notice
  // promises exactly what happens.
  const target = returnPathFrom(state) ?? peekReturnPath()
  if (target?.startsWith("/invite/")) return "auth.notice.signInToAcceptInvite"
  if (target) return "auth.notice.signInToContinue"
  return null
}

export default function Login() {
  const [searchParams] = useSearchParams()
  const location = useLocation()
  // Read once, on mount: `takeSignOutReason` clears what it reads.
  const [noticeKey] = useState(() =>
    noticeKeyFor(searchParams.get("error"), takeSignOutReason(), location.state),
  )
  // Google and an emailed link come back in a fresh page; keep where the
  // visitor was going for /auth/callback (lib/authRedirect).
  useEffect(() => rememberReturnPath(location.state), [location.state])
  const [prefilled] = useState(() => emailFromState(location.state))
  const [form, setForm] = useState<LoginFormData>({ email: prefilled, password: "" })
  const [errors, setErrors] = useState<Partial<Record<keyof LoginFormData, string>>>({})
  const [serverError, setServerError] = useState("")
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [linkSending, setLinkSending] = useState(false)
  const [linkSent, setLinkSent] = useState(false)
  // The address exists and was never confirmed: the error alone left the
  // person with nowhere to go but back to an inbox that may not have it.
  const [unconfirmed, setUnconfirmed] = useState(false)
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)
  const resendCooldown = useCooldown(60, false)
  const { login, signInWithGoogle, sendSignInLink } = useAuth()
  const { t } = useTranslation()

  const handleChange = (field: keyof LoginFormData, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: undefined }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setServerError("")

    const result = makeLoginSchema().safeParse(form)
    if (!result.success) {
      const fieldErrors: typeof errors = {}
      for (const issue of result.error.issues) {
        const key = issue.path[0] as keyof LoginFormData
        if (!fieldErrors[key]) fieldErrors[key] = issue.message
      }
      setErrors(fieldErrors)
      return
    }

    setLoading(true)
    setUnconfirmed(false)
    setResent(false)
    try {
      await login(result.data.email, result.data.password)
    } catch (err) {
      setUnconfirmed(isEmailNotConfirmed(err))
      // Never the server's own words. GoTrue always supplies a `message`,
      // so the `|| t(...)` that used to sit here was unreachable and a
      // German signing in read "Invalid login credentials" on an otherwise
      // entirely German page. The helper also tells "wrong password" apart
      // from "too many attempts", which need different things from the
      // reader.
      setServerError(authErrorMessage(err, "auth.loginFailed"))
    } finally {
      setLoading(false)
    }
  }

  const resendConfirmation = useCallback(async () => {
    setResending(true)
    try {
      await authService.resendConfirmation(form.email.trim())
      setServerError("")
      setResent(true)
      resendCooldown.restart()
    } catch (err) {
      setServerError(authErrorMessage(err, "authRegister.success.resendFailed"))
    } finally {
      setResending(false)
    }
  }, [form.email, resendCooldown])

  /**
   * Ask for a one-time sign-in link.
   *
   * The confirmation is deliberately the same whether or not the address has
   * an account here: anything else turns this form into a way to find out
   * who is registered. A 429 is the one thing worth saying out loud — it is
   * the only outcome the reader can act on, by waiting.
   */
  const handleSignInLink = useCallback(async () => {
    setServerError("")
    const parsed = makeLoginSchema().pick({ email: true }).safeParse({ email: form.email })
    if (!parsed.success) {
      setErrors({ email: parsed.error.issues[0]?.message })
      return
    }

    setLinkSending(true)
    try {
      await sendSignInLink(parsed.data.email)
    } catch (err) {
      if (import.meta.env.DEV) console.error("sendSignInLink failed", err)
      if (isRateLimited(err)) {
        setServerError(authErrorMessage(err, "auth.errors.serverError"))
        setLinkSending(false)
        return
      }
      // Everything else — including "no such user", which is exactly what we
      // must not disclose — reads as the neutral confirmation below.
    }
    setLinkSending(false)
    setLinkSent(true)
  }, [form.email, sendSignInLink])

  const handleGoogleLogin = async () => {
    setGoogleLoading(true)
    try {
      await signInWithGoogle()
    } catch (err) {
      setServerError(authErrorMessage(err, "auth.googleLoginFailed"))
    } finally {
      setGoogleLoading(false)
    }
  }

  if (linkSent) {
    return (
      <AuthLayout heading={t("auth.welcomeBack")}>
        <SignInLinkSent email={form.email} onUsePassword={() => setLinkSent(false)} />
      </AuthLayout>
    )
  }

  return (
    <AuthLayout heading={t("auth.welcomeBack")}>
      <div className="space-y-6 animate-fade-in">
        {/* Not an error of the reader's making, so not in the error colour:
            it explains the page, and steps aside once there is a real error
            to show. */}
        {noticeKey && !serverError && (
          <div role="status" className="text-sm text-ink bg-muted border border-edge p-3 rounded-lg">
            {t(noticeKey)}
          </div>
        )}
        {serverError && (
          <div role="alert" className="text-sm text-destructive-ink bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
            {serverError}
            {unconfirmed && (
              <Button
                type="button"
                variant="link"
                size="sm"
                className="mt-1 h-auto p-0 text-sm"
                onClick={() => void resendConfirmation()}
                disabled={resending || resendCooldown.remaining > 0}
              >
                {resending ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
                ) : (
                  <RefreshCw className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                )}
                {resendCooldown.remaining > 0
                  ? t("authRegister.success.resendIn", { seconds: resendCooldown.remaining })
                  : t("authRegister.success.resend")}
              </Button>
            )}
          </div>
        )}
        {resent && !serverError && (
          <p role="status" className="text-sm text-success-ink">
            {t("authRegister.success.resent")}
          </p>
        )}

        <GoogleButton loading={googleLoading} disabled={loading} onClick={handleGoogleLogin} />

        <OrDivider label={t("auth.orContinueWithEmail")} />

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">{t("auth.email")}</Label>
            <Input
              id="email"
              type="email"
              placeholder={t("auth.emailPlaceholder")}
              autoComplete="email"
              fieldSize="lg"
              value={form.email}
              onChange={(e) => handleChange("email", e.target.value)}
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? "email-error" : undefined}
              autoFocus={!prefilled}
            />
            {errors.email && <p id="email-error" role="alert" className="text-xs text-destructive mt-1">{errors.email}</p>}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">{t("auth.password")}</Label>
              <Link
                to="/forgot-password"
                className="-my-2 inline-flex min-h-[44px] items-center px-1 text-sm text-brand transition-colors hover:text-brand-ink sm:min-h-0 sm:py-0 sm:text-xs"
              >
                {t("auth.forgotPasswordLink")}
              </Link>
            </div>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              fieldSize="lg"
              value={form.password}
              onChange={(e) => handleChange("password", e.target.value)}
              aria-invalid={!!errors.password}
              aria-describedby={errors.password ? "password-error" : undefined}
              autoFocus={!!prefilled}
            />
            {errors.password && <p id="password-error" role="alert" className="text-xs text-destructive mt-1">{errors.password}</p>}
          </div>

          <Button type="submit" size="lg" className="w-full rounded-md font-medium" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
                {t("auth.signingIn")}
              </>
            ) : (
              t("auth.signIn")
            )}
          </Button>

          {/* Quiet, and below the password: for most people the password is
              still the fastest way in, and this is the way out of "I do not
              remember it" that does not involve choosing a new one. */}
          <p className="text-center">
            <button
              type="button"
              onClick={handleSignInLink}
              disabled={linkSending || loading || googleLoading}
              className="inline-flex min-h-[44px] items-center px-1 text-sm text-ink-muted transition-colors hover:text-ink disabled:opacity-60 sm:min-h-0"
            >
              {linkSending ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.75} />{t("auth.signInLinkSending")}</>
              ) : (
                t("auth.signInLink")
              )}
            </button>
          </p>
        </form>

        <p className="text-sm text-center text-ink-muted">
          {t("auth.noAccount")}{" "}
          <Link to="/register" state={location.state} className="text-brand font-medium hover:text-brand-ink transition-colors">
            {t("auth.createOne")}
          </Link>
        </p>
      </div>
    </AuthLayout>
  )
}
