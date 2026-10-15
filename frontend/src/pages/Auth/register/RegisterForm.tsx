import { Link, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import AuthLayout from "@/components/layout/AuthLayout"
import { PasswordFields } from "@/components/auth/PasswordFields"
import { GoogleButton, OrDivider } from "@/components/auth/GoogleButton"
import type { FormState } from "./useRegister"

interface Props {
  form: FormState
  errors: Partial<Record<string, string>>
  serverError: string
  loading: boolean
  googleLoading: boolean
  showPassword: boolean
  passwordGenerated: boolean
  onChange: (field: keyof FormState, value: string) => void
  onSubmit: () => void
  onGoogleSignUp: () => void
  onToggleShowPassword: () => void
  onGeneratePassword: () => void
}

/**
 * The registration form — name, address, one password, and Google above
 * them. Self-signup is student-only (no role
 * selector); teacher accounts are granted via an admin-issued invite
 * (see pages/Invite/AcceptInvite.tsx). Receives state and handlers from
 * `useRegister`; nothing in here owns mutable state.
 */
export function RegisterForm({
  form,
  errors,
  serverError,
  loading,
  googleLoading,
  showPassword,
  passwordGenerated,
  onChange,
  onSubmit,
  onGoogleSignUp,
  onToggleShowPassword,
  onGeneratePassword,
}: Props) {
  const { t } = useTranslation()
  // Where the visitor was going travels to the sign-in page as well.
  const { state } = useLocation()
  return (
    <AuthLayout heading={t("authRegister.heading")}>
      <div className="space-y-6 animate-fade-in">
        {serverError && (
          <div
            role="alert"
            className="text-sm text-destructive-ink bg-destructive/10 border border-destructive/20 p-3 rounded-lg"
          >
            {serverError}
          </div>
        )}

        <GoogleButton loading={googleLoading} disabled={loading} onClick={onGoogleSignUp} />

        <OrDivider label={t("authRegister.orRegisterEmail")} />

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

          <PasswordFields
            idPrefix="reg"
            password={form.password}
            passwordError={errors.password}
            showPassword={showPassword}
            passwordGenerated={passwordGenerated}
            onChange={(value) => onChange("password", value)}
            onToggleShowPassword={onToggleShowPassword}
            onGeneratePassword={onGeneratePassword}
          />

          <Button
            type="submit"
            size="lg"
            className="w-full rounded-md font-medium"
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
            state={state}
            className="text-brand font-medium hover:text-brand-ink transition-colors"
          >
            {t("auth.signIn")}
          </Link>
        </p>
      </div>
    </AuthLayout>
  )
}
