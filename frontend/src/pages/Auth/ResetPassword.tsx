import { useState, useEffect, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { authService } from "@/services/auth"
import AuthLayout from "@/components/layout/AuthLayout"
import { z } from "zod"
import { Loader2, CheckCircle2 } from "lucide-react"
import i18n from "@/i18n/config"

/**
 * Build the schema fresh on each submit so error messages match the
 * currently-active UI language. The factory defers to i18next.t() so
 * switching languages between renders does the right thing.
 */
function makeResetSchema() {
  return z
    .object({
      password: z
        .string()
        .min(6, i18n.t("auth.resetPassword.errors.passwordTooShort")),
      confirmPassword: z.string(),
    })
    .refine((data) => data.password === data.confirmPassword, {
      message: i18n.t("auth.resetPassword.errors.passwordsDoNotMatch"),
      path: ["confirmPassword"],
    })
}

export default function ResetPassword() {
  const { t } = useTranslation()
  const [form, setForm] = useState({ password: "", confirmPassword: "" })
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({})
  const [serverError, setServerError] = useState("")
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const navigate = useNavigate()
  const redirectTimer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    return () => {
      if (redirectTimer.current) clearTimeout(redirectTimer.current)
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setServerError("")

    const result = makeResetSchema().safeParse(form)
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
    } catch (err: unknown) {
      const supaErr = err as { message?: string }
      setServerError(supaErr.message || t("auth.resetPassword.errors.resetFailed"))
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <AuthLayout
        heading={t("auth.resetPassword.successHeading")}
        subheading={t("auth.resetPassword.successSubheading")}
      >
        <div className="flex flex-col items-center text-center gap-4 py-6 animate-fade-in">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-success/10">
            <CheckCircle2 className="h-8 w-8 text-success" strokeWidth={1.75} aria-hidden />
          </div>
          <p className="text-sm text-muted-foreground">
            {t("auth.resetPassword.successBody")}
            <br />
            {t("auth.resetPassword.redirecting")}
          </p>
          <div className="h-1 w-24 rounded-full bg-muted overflow-hidden">
            <div className="animate-grow-bar h-full rounded-full bg-primary" />
          </div>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      heading={t("auth.resetPassword.heading")}
      subheading={t("auth.resetPassword.subheading")}
    >
      <div className="space-y-6 animate-fade-in">
        {serverError && (
          <div role="alert" className="text-sm text-destructive bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
            {serverError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="password">{t("auth.resetPassword.newPassword")}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              fieldSize="lg"
              value={form.password}
              onChange={(e) => {
                setForm((prev) => ({ ...prev, password: e.target.value }))
                setErrors((prev) => ({ ...prev, password: undefined }))
              }}
              aria-invalid={!!errors.password}
              aria-describedby={errors.password ? "reset-password-error" : undefined}
              autoFocus
            />
            {errors.password && (
              <p id="reset-password-error" role="alert" className="text-xs text-destructive mt-1">
                {errors.password}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">{t("auth.resetPassword.confirmNewPassword")}</Label>
            <Input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              fieldSize="lg"
              value={form.confirmPassword}
              onChange={(e) => {
                setForm((prev) => ({ ...prev, confirmPassword: e.target.value }))
                setErrors((prev) => ({ ...prev, confirmPassword: undefined }))
              }}
              aria-invalid={!!errors.confirmPassword}
              aria-describedby={errors.confirmPassword ? "reset-confirm-error" : undefined}
            />
            {errors.confirmPassword && (
              <p id="reset-confirm-error" role="alert" className="text-xs text-destructive mt-1">
                {errors.confirmPassword}
              </p>
            )}
          </div>

          <Button type="submit" size="lg" className="bg-cta-glow w-full font-medium" disabled={loading}>
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
