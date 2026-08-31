import { useTranslation } from "react-i18next"
import { Check, Circle } from "lucide-react"
import { cn } from "@/lib/utils"
import { PASSWORD_MIN_LENGTH, checkPassword, type PasswordRuleId } from "@/lib/passwordPolicy"

interface Props {
  password: string
  confirmPassword: string
  /** Wired into the password input's `aria-describedby`. */
  id?: string
  className?: string
}

/** Literal keys, not `t(\`auth.passwordPolicy.rule${id}\`)` — see docs/I18N.md. */
function ruleLabel(id: PasswordRuleId): string {
  switch (id) {
    case "length":
      return "auth.passwordPolicy.ruleLength"
    case "match":
      return "auth.passwordPolicy.ruleMatch"
  }
}

/**
 * What the password has to be, shown while it is being typed.
 *
 * The rules were enforced long before they were stated: the server asked for
 * twelve characters and a password absent from Have I Been Pwned, and the
 * form asked for six and said nothing. So a person met the real rules only
 * as a refusal, with no way to tell which rule they had broken or how close
 * they were to satisfying it.
 *
 * Not an `aria-live` region on purpose. Every keystroke changes this list,
 * and announcing all of them turns typing a password into a stream of
 * interruptions. It is wired to the input through `aria-describedby`
 * instead, so a screen reader reads the rules on focus, and each row carries
 * its own state in text rather than in colour alone.
 */
export function PasswordRequirements({ password, confirmPassword, id, className }: Props) {
  const { t } = useTranslation()
  const rules = checkPassword(password, confirmPassword)

  return (
    <div id={id} className={cn("space-y-1.5", className)}>
      <ul className="space-y-1">
        {rules.map((rule) => (
          <li key={rule.id} className="flex items-center gap-2 text-xs">
            {rule.met ? (
              <Check className="h-4 w-4 shrink-0 text-success-ink" strokeWidth={1.75} aria-hidden="true" />
            ) : (
              <Circle className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
            )}
            <span className={rule.met ? "text-success-ink" : "text-ink-muted"}>
              {t(ruleLabel(rule.id), { count: PASSWORD_MIN_LENGTH })}
            </span>
            <span className="sr-only">
              {rule.met ? t("auth.passwordPolicy.ruleMet") : t("auth.passwordPolicy.ruleNotMet")}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-ink-muted">{t("auth.passwordPolicy.leakedNote")}</p>
    </div>
  )
}
