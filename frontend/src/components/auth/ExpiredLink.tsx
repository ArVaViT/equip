import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { makeEmailSchema } from "@/lib/validations/auth"
import { emailSendErrorMessage, isRateLimited } from "@/lib/authError"

interface Props {
  /** Mails a fresh link to the address. */
  send: (email: string) => Promise<void>
}

/**
 * A link that no longer signs anybody in, and the way to a new one on the
 * same screen.
 *
 * It used to be a red «!», a sentence, and a redirect to the sign-in page
 * three seconds later — where the one thing the person needed, a new link,
 * was not on offer. The confirmation is the same whether or not the address
 * has an account, so this cannot be used to find out who is registered; a
 * rate limit is the only refusal worth naming.
 */
export function ExpiredLink({ send }: Props) {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [error, setError] = useState("")
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const parsed = makeEmailSchema().safeParse({ email })
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "")
      return
    }
    setError("")
    setSending(true)
    try {
      await send(parsed.data.email)
      setSent(true)
    } catch (err) {
      if (isRateLimited(err)) setError(emailSendErrorMessage(err))
      else setSent(true)
    } finally {
      setSending(false)
    }
  }

  if (sent) {
    return (
      <p role="status" className="text-sm leading-relaxed text-ink-muted animate-fade-in">
        {t("auth.signInLinkSent")}
      </p>
    )
  }

  return (
    <form onSubmit={submit} className="space-y-4 animate-fade-in" noValidate>
      <p role="alert" className="text-sm text-ink">
        {t("auth.errors.linkExpired")}
      </p>
      <div className="space-y-2">
        <Label htmlFor="expired-email">{t("auth.email")}</Label>
        <Input
          id="expired-email"
          type="email"
          autoComplete="email"
          fieldSize="lg"
          placeholder={t("auth.emailPlaceholder")}
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
            setError("")
          }}
          aria-invalid={!!error}
          aria-describedby={error ? "expired-email-error" : undefined}
        />
        {error && (
          <p id="expired-email-error" role="alert" className="text-xs text-destructive">
            {error}
          </p>
        )}
      </div>
      <Button type="submit" size="lg" className="w-full" disabled={sending}>
        {sending && <Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
        {t("auth.sendNewLink")}
      </Button>
    </form>
  )
}
