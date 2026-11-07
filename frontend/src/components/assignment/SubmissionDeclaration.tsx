import { useTranslation } from "react-i18next"
import { Input } from "@/components/ui/input"
import type { AiPolicy } from "@/types"
import { type AiUse, type DeclarationState, declarationPolicyKey } from "./declarationStatement"

export type { DeclarationState }

/**
 * What the student says about this piece of work, before they hand it in.
 *
 * One line of rule and one answer, «Без ИИ» or «С ИИ». The three-paragraph
 * reminder with two checkboxes that stood here was read by nobody and
 * handed in by nobody: in the whole life of the platform not one written
 * work arrived. The finding behind the long form (a reminder carrying the
 * rule, an example and the consequence) still stands; the example and the
 * consequence now live in the course's own description of its rule, and the
 * screen where the work is handed in asks the one thing only the student
 * can answer. Pressing «Отправить» is the confirmation — the sentence above
 * the button says so, and it is stored with the answer.
 *
 * Never pre-answered: the choice is theirs to make, and the submit button
 * does nothing until it is made.
 */
export function SubmissionDeclaration({
  policy,
  value,
  onChange,
}: {
  policy: AiPolicy
  value: DeclarationState
  onChange: (next: DeclarationState) => void
}) {
  const { t } = useTranslation()
  // Nothing to declare, so nothing is asked. Showing a question on a course
  // with no rule would train students to tap past it on the courses that have one.
  if (policy === "ai_open") return null

  const key = declarationPolicyKey(policy)
  const choices: { aiUse: AiUse; label: string }[] = [
    { aiUse: "none", label: t("declaration.withoutAi") },
    { aiUse: "assisted", label: t("declaration.withAi") },
  ]

  return (
    <div className="space-y-2">
      <p id="declaration-rule" className="text-sm text-ink-muted">
        {t(`declaration.${key}.rule`)}
      </p>
      <div role="radiogroup" aria-labelledby="declaration-rule" className="grid grid-cols-2 gap-2">
        {choices.map((choice) => {
          const chosen = value.aiUse === choice.aiUse
          return (
            <button
              key={choice.aiUse}
              type="button"
              role="radio"
              aria-checked={chosen}
              onClick={() => onChange({ ...value, aiUse: choice.aiUse })}
              className={`min-h-11 rounded-lg border px-3 text-sm font-medium transition-colors ${
                chosen
                  ? "border-brand bg-brand text-brand-foreground"
                  : "border-edge bg-surface text-ink hover:bg-muted/40"
              }`}
            >
              {choice.label}
            </button>
          )
        })}
      </div>
      {policy === "ai_with_disclosure" && value.aiUse === "assisted" && (
        // Their own sentence. Sitting next to the essay it tells a teacher
        // more than any detector would, and it is the entire reason
        // disclosure is the default rather than a ban.
        <Input
          value={value.note}
          onChange={(e) => onChange({ ...value, note: e.target.value })}
          placeholder={t("declaration.notePlaceholder")}
          aria-label={t("declaration.note")}
          fieldSize="default"
        />
      )}
    </div>
  )
}
