import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { ArrowLeft, Loader2, MailCheck, RefreshCw } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import AuthLayout from "@/components/layout/AuthLayout"
import { authService } from "@/services/auth"
import { authErrorMessage } from "@/lib/authError"

interface Props {
  email: string
}

/**
 * Post-register confirmation screen.
 *
 * It used to be a dead end: "check your email", and nothing to do if the
 * email never came. That is the busiest failure this product has — six of
 * the seven accounts ever created with a password never confirmed — and the
 * person was left with a page offering only "back to sign in", which is
 * exactly what they cannot do yet.
 *
 * So: a resend button, the spam folder named out loud, and how long the
 * link lasts. Supabase enforces one email per minute per address
 * (`smtp_max_frequency`), so the button counts down rather than letting
 * somebody hammer it into a 429 they cannot interpret.
 */
const RESEND_COOLDOWN_SECONDS = 60

export function SuccessView({ email }: Props) {
  const { t } = useTranslation()
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS)
  const [sending, setSending] = useState(false)
  const [resent, setResent] = useState(false)
  const [error, setError] = useState("")
  const timer = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    // Starts on arrival: the first email left a moment ago, so the button is
    // never offered at a time the server would refuse it anyway.
    timer.current = setInterval(() => {
      setCooldown((seconds) => (seconds <= 1 ? 0 : seconds - 1))
    }, 1000)
    return () => clearInterval(timer.current)
  }, [])

  const resend = useCallback(async () => {
    setSending(true)
    setError("")
    try {
      await authService.resendConfirmation(email)
      setResent(true)
      setCooldown(RESEND_COOLDOWN_SECONDS)
    } catch (err) {
      setError(authErrorMessage(err, "authRegister.success.resendFailed"))
    } finally {
      setSending(false)
    }
  }, [email])

  return (
    <AuthLayout
      heading={t("authRegister.success.headingDefault")}
      subheading={t("authRegister.success.subheadingDefault")}
    >
      <div className="space-y-6 animate-fade-in">
        <div className="flex flex-col items-center text-center gap-4 py-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-md bg-brand/10">
            <MailCheck className="h-8 w-8 text-brand-ink" strokeWidth={1.75} aria-hidden />
          </div>
          <div className="space-y-2">
            <p className="text-sm text-ink-muted leading-relaxed">
              <Trans
                i18nKey="authRegister.success.body"
                values={{ email }}
                components={{ strong: <strong className="text-ink" /> }}
              />
              <br />
              {t("authRegister.success.clickLinkToActivate")}
            </p>
            {/* Named out loud, because it is where the email most often is. */}
            <p className="text-xs text-ink-muted">{t("authRegister.success.checkSpam")}</p>
          </div>
        </div>

        <div className="space-y-3">
          {resent && !error && (
            <p role="status" className="text-center text-sm text-success-ink">
              {t("authRegister.success.resent")}
            </p>
          )}
          {error && (
            <p role="alert" className="text-center text-sm text-destructive-ink">
              {error}
            </p>
          )}

          <Button
            type="button"
            variant="outline"
            size="lg"
            className="w-full"
            disabled={sending || cooldown > 0}
            onClick={() => void resend()}
          >
            {sending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} aria-hidden />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" strokeWidth={1.75} aria-hidden />
            )}
            {cooldown > 0
              ? t("authRegister.success.resendIn", { seconds: cooldown })
              : t("authRegister.success.resend")}
          </Button>

          <Link to="/login" className="block">
            <Button variant="ghost" size="lg" className="w-full">
              <ArrowLeft className="h-4 w-4 mr-2" strokeWidth={1.75} aria-hidden />
              {t("authRegister.success.backToSignIn")}
            </Button>
          </Link>
        </div>
      </div>
    </AuthLayout>
  )
}
