import { useCallback, useState } from "react"
import { Link } from "react-router-dom"
import { Loader2, MailCheck, RefreshCw } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import AuthLayout from "@/components/layout/AuthLayout"
import { authService } from "@/services/auth"
import { emailSendErrorMessage } from "@/lib/authError"
import { useCooldown } from "@/hooks/useCooldown"

/** Supabase refuses a second mail to one address inside `smtp_max_frequency` (60s). */
const RESEND_COOLDOWN_SECONDS = 60

interface Props {
  email: string
  /** The address already had an unconfirmed account; its first password stands. */
  repeated: boolean
  onChangeAddress: () => void
}

/**
 * After «create account»: one line that says everything that matters, a
 * resend that counts down, and a way to fix a mistyped address.
 *
 * «Only the latest email works» is said out loud because it is true and
 * nobody would guess it: every send issues a new link and voids the earlier
 * ones, so a person with three mails who opens the first meets «link
 * expired».
 *
 * A repeated sign-up gets the truth as well: Supabase sent a new mail but
 * kept the password from the first attempt, so the one just typed will not
 * work. A password reset both sets a new one and confirms the address.
 */
export function SuccessView({ email, repeated, onChangeAddress }: Props) {
  const { t } = useTranslation()
  const { remaining, restart } = useCooldown(RESEND_COOLDOWN_SECONDS)
  const [sending, setSending] = useState(false)
  const [resent, setResent] = useState(false)
  const [error, setError] = useState("")

  const resend = useCallback(async () => {
    setSending(true)
    setError("")
    try {
      await authService.resendConfirmation(email)
      setResent(true)
      restart()
    } catch (err) {
      setError(emailSendErrorMessage(err))
    } finally {
      setSending(false)
    }
  }, [email, restart])

  const strong = { strong: <strong className="text-ink" /> }

  return (
    <AuthLayout heading={t("authRegister.success.headingDefault")}>
      <div className="space-y-6 animate-fade-in">
        <div className="flex flex-col items-center text-center gap-4 py-2">
          <div className="flex h-16 w-16 items-center justify-center rounded-md bg-brand/10">
            <MailCheck className="h-8 w-8 text-brand-ink" strokeWidth={1.75} aria-hidden />
          </div>
          <p className="text-sm text-ink-muted leading-relaxed">
            <Trans i18nKey="authRegister.success.line" values={{ email }} components={strong} />
          </p>
          {repeated && (
            <p className="text-sm text-ink-muted leading-relaxed">
              <Trans
                i18nKey="authRegister.success.repeated"
                components={{
                  reset: (
                    <Link
                      to="/forgot-password"
                      state={{ email }}
                      className="font-medium text-brand hover:text-brand-ink"
                    />
                  ),
                }}
              />
            </p>
          )}
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
            disabled={sending || remaining > 0}
            onClick={() => void resend()}
          >
            {sending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} aria-hidden />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" strokeWidth={1.75} aria-hidden />
            )}
            {remaining > 0
              ? t("authRegister.success.resendIn", { seconds: remaining })
              : t("authRegister.success.resend")}
          </Button>

          <p className="text-center">
            <button
              type="button"
              onClick={onChangeAddress}
              className="inline-flex min-h-[44px] items-center px-1 text-sm text-ink-muted transition-colors hover:text-ink sm:min-h-0"
            >
              {t("authRegister.success.changeAddress")}
            </button>
          </p>
        </div>
      </div>
    </AuthLayout>
  )
}
