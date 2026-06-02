import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import AuthLayout from "@/components/layout/AuthLayout"
import { GoogleIcon } from "./GoogleIcon"
import type { FormState } from "./useRegister"

interface Props {
  form: FormState
  errors: Partial<Record<string, string>>
  serverError: string
  loading: boolean
  googleLoading: boolean
  onChange: (field: keyof FormState, value: string) => void
  onSubmit: () => void
  onGoogleSignUp: () => void
}

/**
 * The actual registration form — role toggle, four text inputs,
 * Google OAuth shortcut, submit button. Receives state and handlers from
 * `useRegister`; nothing in here owns mutable state.
 */
export function RegisterForm({
  form,
  errors,
  serverError,
  loading,
  googleLoading,
  onChange,
  onSubmit,
  onGoogleSignUp,
}: Props) {
  const { t } = useTranslation()
  return (
    <AuthLayout
      heading={t("authRegister.heading")}
      subheading={t("authRegister.subheading")}
    >
      <div className="space-y-6 animate-fade-in">
        {serverError && (
          <div
            role="alert"
            className="text-sm text-destructive bg-destructive/10 border border-destructive/20 p-3 rounded-lg"
          >
            {serverError}
          </div>
        )}

        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full font-medium rounded-md"
          onClick={onGoogleSignUp}
          disabled={googleLoading || loading}
        >
          {googleLoading ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
              {t("auth.connecting")}
            </>
          ) : (
            <>
              <GoogleIcon className="h-4 w-4 mr-2.5" />
              {t("auth.continueWithGoogle")}
            </>
          )}
        </Button>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-surface px-3 text-ink-muted">
              {t("authRegister.orRegisterEmail")}
            </span>
          </div>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSubmit()
          }}
          className="space-y-4"
        >
          <div className="space-y-2">
            <Label htmlFor="fullName">{t("authRegister.fullName")}</Label>
            <Input
              id="fullName"
              placeholder={t("authRegister.fullNamePlaceholder")}
              autoComplete="name"
              fieldSize="lg"
              value={form.full_name}
              onChange={(e) => onChange("full_name", e.target.value)}
              aria-invalid={!!errors.full_name}
              aria-describedby={errors.full_name ? "fullName-error" : undefined}
              autoFocus
            />
            {errors.full_name && (
              <p
                id="fullName-error"
                role="alert"
                className="text-xs text-destructive mt-1"
              >
                {errors.full_name}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">{t("auth.email")}</Label>
            <Input
              id="email"
              type="email"
              placeholder={t("auth.emailPlaceholder")}
              autoComplete="email"
              fieldSize="lg"
              value={form.email}
              onChange={(e) => onChange("email", e.target.value)}
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? "reg-email-error" : undefined}
            />
            {errors.email && (
              <p
                id="reg-email-error"
                role="alert"
                className="text-xs text-destructive mt-1"
              >
                {errors.email}
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="password">{t("auth.password")}</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                fieldSize="lg"
                value={form.password}
                onChange={(e) => onChange("password", e.target.value)}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "reg-password-error" : undefined}
              />
              {errors.password && (
                <p
                  id="reg-password-error"
                  role="alert"
                  className="text-xs text-destructive mt-1"
                >
                  {errors.password}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">{t("authRegister.confirmPasswordShort")}</Label>
              <Input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                fieldSize="lg"
                value={form.confirmPassword}
                onChange={(e) => onChange("confirmPassword", e.target.value)}
                aria-invalid={!!errors.confirmPassword}
                aria-describedby={
                  errors.confirmPassword ? "confirmPassword-error" : undefined
                }
              />
              {errors.confirmPassword && (
                <p
                  id="confirmPassword-error"
                  role="alert"
                  className="text-xs text-destructive mt-1"
                >
                  {errors.confirmPassword}
                </p>
              )}
            </div>
          </div>

          <Button
            type="submit"
            size="lg"
            className="cta-glow w-full font-medium rounded-md"
            disabled={loading}
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
                {t("authRegister.creatingAccount")}
              </>
            ) : (
              t("authRegister.createAccount")
            )}
          </Button>
        </form>

        <p className="text-sm text-center text-ink-muted">
          {t("authRegister.alreadyHaveAccount")}{" "}
          <Link
            to="/login"
            className="text-brand font-medium hover:text-brand/80 transition-colors"
          >
            {t("auth.signIn")}
          </Link>
        </p>
      </div>
    </AuthLayout>
  )
}
