import { useState } from "react"
import { Link } from "react-router-dom"
import { Trans, useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/useAuth"
import AuthLayout from "@/components/layout/AuthLayout"
import { ArrowLeft, Loader2, MailCheck } from "lucide-react"

export default function ForgotPassword() {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
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
      if (import.meta.env.DEV) console.error("resetPassword failed", err)
      setError(t("auth.forgotPassword.errors.sendFailed"))
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
            <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
              <MailCheck className="h-8 w-8 text-primary" strokeWidth={1.75} aria-hidden />
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              <Trans
                i18nKey="auth.forgotPassword.sentBody"
                values={{ email }}
                components={{ strong: <strong className="text-foreground" /> }}
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
          <div role="alert" className="text-sm text-destructive bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
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
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {t("auth.forgotPassword.sending")}
              </>
            ) : (
              t("auth.forgotPassword.submit")
            )}
          </Button>
        </form>

        <Link
          to="/login"
          className="flex items-center justify-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {t("auth.forgotPassword.backToSignIn")}
        </Link>
      </div>
    </AuthLayout>
  )
}
