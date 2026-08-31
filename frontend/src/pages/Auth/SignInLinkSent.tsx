import { useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2, MailCheck, RotateCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { authService } from "@/services/auth"
import { authErrorMessage } from "@/lib/authError"
import { useCooldown } from "@/hooks/useCooldown"

const RESEND_COOLDOWN_SECONDS = 60

interface Props {
  email: string
  onUsePassword: () => void
}

/**
 * What the reader sees after asking for a sign-in link.
 *
 * The sentence never confirms whether the address has an account — the form
 * that leads here must not double as a way to find out who is registered —
 * so it says "if we have that address". The repeat button counts down
 * because Supabase refuses a second email inside `smtp_max_frequency`.
 */
export function SignInLinkSent({ email, onUsePassword }: Props) {
  const { t } = useTranslation()
  const { remaining, restart } = useCooldown(RESEND_COOLDOWN_SECONDS)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState("")

  const resend = useCallback(async () => {
    setSending(true)
    setError("")
    try {
      await authService.sendSignInLink(email)
      restart()
    } catch (err) {
      if (import.meta.env.DEV) console.error("sendSignInLink failed", err)
      const message = authErrorMessage(err, "auth.errors.serverError")
      // Same disclosure rule as the first send: only a rate limit is worth
      // naming, because waiting is the one thing the reader can do about it.
      if (message === t("auth.errors.rateLimited")) setError(message)
      else restart()
    } finally {
      setSending(false)
    }
  }, [email, restart, t])

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col items-center gap-4 py-4 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-md bg-brand/10">
          <MailCheck className="h-8 w-8 text-brand-ink" strokeWidth={1.75} aria-hidden />
        </div>
        <p className="text-sm leading-relaxed text-ink-muted">{t("auth.signInLinkSent")}</p>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive-ink">
          {error}
        </div>
      )}

      <Button
        type="button"
        variant="outline"
        size="lg"
        className="w-full rounded-md font-medium"
        onClick={resend}
        disabled={sending || remaining > 0}
      >
        {sending ? (
          <><Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.75} />{t("auth.signInLinkSending")}</>
        ) : remaining > 0 ? (
          <><RotateCw className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden />{t("auth.signInLinkAgainIn", { seconds: remaining })}</>
        ) : (
          <><RotateCw className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden />{t("auth.signInLinkAgain")}</>
        )}
      </Button>

      <p className="text-center">
        <button
          type="button"
          onClick={onUsePassword}
          className="text-sm font-medium text-brand transition-colors hover:text-brand-ink"
        >
          {t("auth.signInLinkBackToPassword")}
        </button>
      </p>
    </div>
  )
}
