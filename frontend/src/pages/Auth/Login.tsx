import { useCallback, useEffect, useState } from "react"
import { Link, useLocation, useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/useAuth"
import { makeLoginSchema, type LoginFormData } from "@/lib/validations/auth"
import AuthLayout from "@/components/layout/AuthLayout"
import { ChevronDown, Loader2, RefreshCw } from "lucide-react"
import { authErrorMessage, emailSendErrorMessage, isEmailNotConfirmed, isInvalidCredentials } from "@/lib/authError"
import { GoogleButton, OrDivider } from "@/components/auth/GoogleButton"
import { authService } from "@/services/auth"
import { useCooldown } from "@/hooks/useCooldown"
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
  if (error === "oauth_timeout") return "auth.callback.timedOut"
  // The same target the public gate will use after sign-in, so the notice
  // promises exactly what happens.
  const target = returnPathFrom(state) ?? peekReturnPath()
  if (target?.startsWith("/invite/")) return "auth.notice.signInToAcceptInvite"
  if (target) return "auth.notice.signInToContinue"
  return null
}

/**
 * Wrong passwords in a row before «Forgot password?» is offered. Most people
 * mistype once and get it on the next try; a link to a reset that early is
 * one more thing to read on a screen whose job is to get them in.
 */
export const FORGOT_PASSWORD_AFTER = 3

/**
 * Set on this device after a password sign-in, so the person who always uses
 * email does not have to open the form every visit. A convenience only:
 * storage can be off or cleared, and then the form simply starts closed.
 */
const EMAIL_SIGN_IN_KEY = "equip.signIn.email"

function usedEmailBefore(): boolean {
  try {
    return localStorage.getItem(EMAIL_SIGN_IN_KEY) === "1"
  } catch {
    return false
  }
}

function rememberEmailSignIn() {
  try {
    localStorage.setItem(EMAIL_SIGN_IN_KEY, "1")
  } catch {
    // Private mode or blocked storage: next visit starts with the form closed.
  }
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
  // Three of every four people here sign in with Google, so the email form
  // waits behind «or sign in with email» instead of filling the screen. It
  // starts open when there is an address to finish (an invitation) or when
  // this device signed in with a password before.
  const [emailOpen, setEmailOpen] = useState(() => !!prefilled || usedEmailBefore())
  const [wrongPasswords, setWrongPasswords] = useState(0)
  const [form, setForm] = useState<LoginFormData>({ email: prefilled, password: "" })
  const [errors, setErrors] = useState<Partial<Record<keyof LoginFormData, string>>>({})
  const [serverError, setServerError] = useState("")
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  // The address exists and was never confirmed: the error alone left the
  // person with nowhere to go but back to an inbox that may not have it.
  const [unconfirmed, setUnconfirmed] = useState(false)
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)
  const resendCooldown = useCooldown(60, false)
  const { login, signInWithGoogle } = useAuth()
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
      rememberEmailSignIn()
    } catch (err) {
      setUnconfirmed(isEmailNotConfirmed(err))
      if (isInvalidCredentials(err)) setWrongPasswords((n) => n + 1)
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
      setServerError(emailSendErrorMessage(err))
    } finally {
      setResending(false)
    }
  }, [form.email, resendCooldown])

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

        {emailOpen ? (
          <OrDivider label={t("auth.orContinueWithEmail")} />
        ) : (
          // The same divider, words and all, so the screen reads as it always
          // did; only now the words are the way in.
          <OrDivider
            label={
              <button
                type="button"
                onClick={() => setEmailOpen(true)}
                aria-expanded={false}
                aria-controls="email-sign-in"
                className="-my-3 inline-flex min-h-[44px] items-center gap-1 uppercase text-ink-muted transition-colors hover:text-ink focus-visible:text-ink"
              >
                {t("auth.orContinueWithEmail")}
                <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </button>
            }
          />
        )}

        {emailOpen && (
          <form id="email-sign-in" onSubmit={handleSubmit} className="space-y-4 animate-fade-in">
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
                {/* Only after a few misses: on the first try it is one more
                    thing to read on a screen whose job is to get you in. */}
                {wrongPasswords >= FORGOT_PASSWORD_AFTER && (
                  <Link
                    to="/forgot-password"
                    state={{ email: form.email.trim() }}
                    className="-my-2 inline-flex min-h-[44px] items-center px-1 text-sm text-brand transition-colors hover:text-brand-ink sm:min-h-0 sm:py-0 sm:text-xs"
                  >
                    {t("auth.forgotPasswordLink")}
                  </Link>
                )}
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
          </form>
        )}

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
