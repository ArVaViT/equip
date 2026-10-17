import { useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { Trans, useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/useAuth"
import AuthLayout from "@/components/layout/AuthLayout"
import { emailSendErrorMessage } from "@/lib/authError"
import { emailFromState } from "@/lib/authRedirect"
import { ArrowLeft, Loader2, MailCheck } from "lucide-react"

export default function ForgotPassword() {
  const { t } = useTranslation()
  const location = useLocation()
  const [email, setEmail] = useState(() => emailFromState(location.state))
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const { resetPassword } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    const trimmed = email.trim()
    if (!trimmed) {
      setError(t("auth.forgotPassword.errors.emailRequired"))
      return
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setError(t("auth.forgotPassword.errors.emailInvalid"))
      return
    }

    setLoading(true)
    try {
      await resetPassword(trimmed)
      setSent(true)
    } catch (err: unknown) {
      // A refused repeat, the hourly allowance, a hook that failed: each
      // has its own sentence, and none of them reads as «the site is down»
      // (`emailSendErrorMessage`). No disclosure either way — GoTrue answers
      // 200 for an address it does not hold.
      setError(emailSendErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <AuthLayout
        heading={t("auth.forgotPassword.sentHeading")}
        subheading={t("auth.forgotPassword.sentSubheading")}
      >
        <div className="space-y-6 animate-fade-in">
          <div className="flex flex-col items-center text-center gap-4 py-4">
            <div className="h-16 w-16 rounded-full bg-brand/10 flex items-center justify-center">
              <MailCheck className="h-8 w-8 text-brand-ink" strokeWidth={1.75} aria-hidden />
            </div>
            <p className="text-sm text-ink-muted leading-relaxed">
              <Trans
                i18nKey="auth.forgotPassword.sentBody"
                values={{ email }}
                components={{ strong: <strong className="text-ink" /> }}
              />
            </p>
          </div>
          <Link to="/login" className="block">
            <Button variant="outline" size="lg" className="w-full">
              <ArrowLeft className="h-4 w-4 mr-2" strokeWidth={1.75} aria-hidden />
              {t("auth.forgotPassword.backToSignIn")}
            </Button>
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      heading={t("auth.forgotPassword.heading")}
      subheading={t("auth.forgotPassword.subheading")}
    >
      <div className="space-y-6 animate-fade-in">
        {error && (
          <div role="alert" className="text-sm text-destructive-ink bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">{t("auth.forgotPassword.emailLabel")}</Label>
            <Input
              id="email"
              type="email"
              placeholder={t("auth.emailPlaceholder")}
              autoComplete="email"
              fieldSize="lg"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoFocus
            />
          </div>

          <Button type="submit" size="lg" className="w-full font-medium" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
                {t("auth.forgotPassword.sending")}
              </>
            ) : (
              t("auth.forgotPassword.submit")
            )}
          </Button>
        </form>

        <Link
          to="/login"
          className="flex items-center justify-center gap-1.5 text-sm text-ink-muted hover:text-brand transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {t("auth.forgotPassword.backToSignIn")}
        </Link>
      </div>
    </AuthLayout>
  )
}
