import { useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/useAuth"
import { makeLoginSchema, type LoginFormData } from "@/lib/validations/auth"
import AuthLayout from "@/components/layout/AuthLayout"
import { Loader2 } from "lucide-react"
import { authErrorMessage } from "@/lib/authError"
import { GoogleIcon } from "./register/GoogleIcon"

export default function Login() {
  const [form, setForm] = useState<LoginFormData>({ email: "", password: "" })
  const [errors, setErrors] = useState<Partial<Record<keyof LoginFormData, string>>>({})
  const [serverError, setServerError] = useState("")
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
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
    try {
      await login(result.data.email, result.data.password)
    } catch (err) {
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
    <AuthLayout heading={t("auth.welcomeBack")} subheading={t("auth.signInSubheading")}>
      <div className="space-y-6 animate-fade-in">
        {serverError && (
          <div role="alert" className="text-sm text-destructive-ink bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
            {serverError}
          </div>
        )}

        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full font-medium rounded-md"
          onClick={handleGoogleLogin}
          disabled={googleLoading || loading}
        >
          {googleLoading ? (
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />{t("auth.connecting")}</>
          ) : (
            <><GoogleIcon className="h-4 w-4 mr-2.5" />{t("auth.continueWithGoogle")}</>
          )}
        </Button>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-surface px-3 text-ink-muted">{t("auth.orContinueWithEmail")}</span>
          </div>
        </div>

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
              autoFocus
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

        <p className="text-sm text-center text-ink-muted">
          {t("auth.noAccount")}{" "}
          <Link to="/register" className="text-brand font-medium hover:text-brand-ink transition-colors">
            {t("auth.createOne")}
          </Link>
        </p>
      </div>
    </AuthLayout>
  )
}
