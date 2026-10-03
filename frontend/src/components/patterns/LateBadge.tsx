import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"

/**
 * «Handed in late», wherever a piece of work is shown.
 *
 * One component so the student's panel, the teacher's grader, the marking
 * queue and the quiz review all say it the same way — and so that the word
 * stays a quiet warning and never becomes a verdict. Late work is accepted;
 * what it costs is the teacher's decision, and this only makes sure they
 * know (2026-10-03).
 */
export function LateBadge({ className }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <Badge variant="warningSubtle" className={className}>
      {t("common.late")}
    </Badge>
  )
}
