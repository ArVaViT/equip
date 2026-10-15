import { useTranslation } from "react-i18next"
import { Check, Circle, Eye, EyeOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PASSWORD_MIN_LENGTH, isLongEnough } from "@/lib/passwordPolicy"

interface Props {
  password: string
  passwordError?: string
  /** Distinguishes the ids when two of these ever share a page. */
  idPrefix: string
  /** Reset-password says "new password"; the others just say "password". */
  label?: string
  showPassword: boolean
  passwordGenerated: boolean
  onChange: (value: string) => void
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
 * One field, not two. The second field was there to catch a typo nobody can
 * see; the eye shows the password instead, and the generator fills it in and
 * shows it. The rule that can be checked while typing — the length — sits
 * under the field with its state in text as well as in the icon; the breach
 * check cannot be answered by a browser, and a refused password says so on
 * submit.
 */
export function PasswordFields({
  password,
  passwordError,
  idPrefix,
  label,
  showPassword,
  passwordGenerated,
  onChange,
  onToggleShowPassword,
  onGeneratePassword,
}: Props) {
  const { t } = useTranslation()
  const passwordId = `${idPrefix}-password`
  const ruleId = `${idPrefix}-password-rule`
  const passwordErrorId = `${idPrefix}-password-error`
  const longEnough = isLongEnough(password)

  return (
    <div className="space-y-2">
      <Label htmlFor={passwordId}>{label ?? t("auth.password")}</Label>
      <div className="relative">
        <Input
          id={passwordId}
          type={showPassword ? "text" : "password"}
          autoComplete="new-password"
          fieldSize="lg"
          className="pr-10"
          value={password}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={!!passwordError}
          aria-describedby={passwordError ? `${passwordErrorId} ${ruleId}` : ruleId}
        />
        <button
          type="button"
          onClick={onToggleShowPassword}
          aria-label={showPassword ? t("auth.passwordPolicy.hide") : t("auth.passwordPolicy.show")}
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
        <p id={passwordErrorId} role="alert" className="text-xs text-destructive">
          {passwordError}
        </p>
      )}

      <div className="flex items-center justify-between gap-3">
        {/* Not an `aria-live` region: it changes on every keystroke. Wired to
            the input through `aria-describedby`, so it is read on focus. */}
        <p id={ruleId} className="flex items-center gap-1.5 text-xs">
          {longEnough ? (
            <Check className="h-4 w-4 shrink-0 text-success-ink" strokeWidth={1.75} aria-hidden="true" />
          ) : (
            <Circle className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
          )}
          <span className={longEnough ? "text-success-ink" : "text-ink-muted"}>
            {t("auth.passwordPolicy.ruleLength", { count: PASSWORD_MIN_LENGTH })}
          </span>
          <span className="sr-only">
            {longEnough ? t("auth.passwordPolicy.ruleMet") : t("auth.passwordPolicy.ruleNotMet")}
          </span>
        </p>
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
