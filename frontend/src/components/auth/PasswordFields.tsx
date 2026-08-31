import { useTranslation } from "react-i18next"
import { Eye, EyeOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordRequirements } from "@/components/auth/PasswordRequirements"

interface Props {
  password: string
  confirmPassword: string
  passwordError?: string
  confirmError?: string
  /** Distinguishes the ids when two of these ever share a page. */
  idPrefix: string
  /** Reset-password says "new password"; the others just say "password". */
  passwordLabel?: string
  confirmLabel?: string
  showPassword: boolean
  passwordGenerated: boolean
  onChange: (field: "password" | "confirmPassword", value: string) => void
  onToggleShowPassword: () => void
  onGeneratePassword: () => void
}

/**
 * "Choose a password", once, for all three screens that ask.
 *
 * Register, accept-invite and reset-password each had their own copy of
 * this markup, and each had its own idea of the rules — all three asked for
 * six characters while Supabase Auth enforced twelve plus a breach check.
 * Three copies is how the screens came to disagree with the server and with
 * each other, so there is one now.
 *
 * Both fields reveal together: an unmasked password beside a masked
 * confirmation is a field you still cannot check by eye.
 */
export function PasswordFields({
  password,
  confirmPassword,
  passwordError,
  confirmError,
  idPrefix,
  passwordLabel,
  confirmLabel,
  showPassword,
  passwordGenerated,
  onChange,
  onToggleShowPassword,
  onGeneratePassword,
}: Props) {
  const { t } = useTranslation()
  const passwordId = `${idPrefix}-password`
  const confirmId = `${idPrefix}-confirmPassword`
  const requirementsId = `${idPrefix}-password-requirements`
  const passwordErrorId = `${idPrefix}-password-error`
  const confirmErrorId = `${idPrefix}-confirmPassword-error`

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor={passwordId}>{passwordLabel ?? t("auth.password")}</Label>
          <div className="relative">
            <Input
              id={passwordId}
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              fieldSize="lg"
              className="pr-10"
              value={password}
              onChange={(e) => onChange("password", e.target.value)}
              aria-invalid={!!passwordError}
              aria-describedby={
                passwordError ? `${passwordErrorId} ${requirementsId}` : requirementsId
              }
            />
            <button
              type="button"
              onClick={onToggleShowPassword}
              aria-label={
                showPassword ? t("auth.passwordPolicy.hide") : t("auth.passwordPolicy.show")
              }
              aria-pressed={showPassword}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-sm text-ink-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
            >
              {showPassword ? (
                <EyeOff className="h-4 w-4" strokeWidth={1.75} />
              ) : (
                <Eye className="h-4 w-4" strokeWidth={1.75} />
              )}
            </button>
          </div>
          {passwordError && (
            <p id={passwordErrorId} role="alert" className="text-xs text-destructive mt-1">
              {passwordError}
            </p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor={confirmId}>{confirmLabel ?? t("authRegister.confirmPasswordShort")}</Label>
          <Input
            id={confirmId}
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            fieldSize="lg"
            value={confirmPassword}
            onChange={(e) => onChange("confirmPassword", e.target.value)}
            aria-invalid={!!confirmError}
            aria-describedby={confirmError ? confirmErrorId : undefined}
          />
          {confirmError && (
            <p id={confirmErrorId} role="alert" className="text-xs text-destructive mt-1">
              {confirmError}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-start justify-between gap-3">
        <PasswordRequirements
          id={requirementsId}
          password={password}
          confirmPassword={confirmPassword}
          className="flex-1"
        />
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto shrink-0 p-0 text-xs"
          onClick={onGeneratePassword}
        >
          {t("auth.passwordPolicy.generate")}
        </Button>
      </div>

      {passwordGenerated && (
        <p role="status" className="text-xs text-success-ink">
          {t("auth.passwordPolicy.generated")}
        </p>
      )}
    </div>
  )
}
