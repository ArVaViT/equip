import { useTranslation } from "react-i18next"
import { ShieldCheck } from "lucide-react"
import { Textarea } from "@/components/ui/textarea"
import type { AiPolicy } from "@/types"

export interface DeclarationState {
  confirmed: boolean
  usedAi: boolean
  note: string
}

/**
 * What the student says about this piece of work, before they hand it in.
 *
 * Three parts, together, and the grouping is not decorative. A 2023
 * double-blind randomised field study of unproctored online exams — this
 * school's exact setting — found that a reminder before the work reduced
 * cheating when it carried the **policy**, an **example of what integrity
 * means here**, and the **consequences**. Any one of the three alone is a
 * checkbox.
 *
 * It is deliberately not built on the famous «sign at the top rather than the
 * bottom» result: the original authors published six failed replications in
 * 2020 and the data was later shown to be fabricated.
 *
 * Never pre-ticked, and the submit button does nothing until it is — the same
 * rule the legal agreements follow, for the same reason.
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
  // Nothing to declare, so nothing is asked. Showing a confirmation on a course
  // with no rule would train students to tick past it on the courses that have one.
  if (policy === "ai_open") return null

  const key = policy === "ai_forbidden" ? "ai_forbidden" : "ai_with_disclosure"

  return (
    <div className="rounded-lg border border-edge bg-muted/20 p-3">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <ShieldCheck className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
        {t("declaration.heading")}
      </p>
      <div className="mt-1.5 space-y-1 text-sm text-ink-muted">
        <p>{t(`declaration.${key}.policy`)}</p>
        <p>{t(`declaration.${key}.example`)}</p>
        <p>{t(`declaration.${key}.consequence`)}</p>
      </div>

      <label className="mt-2.5 flex min-h-11 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={value.confirmed}
          onChange={(e) => onChange({ ...value, confirmed: e.target.checked })}
          className="h-4 w-4 rounded border-edge"
        />
        {t("declaration.confirm")}
      </label>

      {policy === "ai_with_disclosure" && (
        <>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={value.usedAi}
              onChange={(e) => onChange({ ...value, usedAi: e.target.checked })}
              className="h-4 w-4 rounded border-edge"
            />
            {t("declaration.usedAi")}
          </label>
          {value.usedAi && (
            // Their own sentence. Sitting next to the essay it tells a teacher
            // more than any detector would, and it is the entire reason
            // disclosure is the default rather than a ban.
            <Textarea
              value={value.note}
              onChange={(e) => onChange({ ...value, note: e.target.value })}
              placeholder={t("declaration.notePlaceholder")}
              aria-label={t("declaration.note")}
              className="mt-1 min-h-[52px] text-sm"
            />
          )}
        </>
      )}
    </div>
  )
}
