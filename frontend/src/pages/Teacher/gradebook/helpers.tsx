import {
  HelpCircle,
  GraduationCap,
  ClipboardList,
  FileText,
} from "lucide-react"
import type { GradeForm } from "./types"

/**
 * Frozen empty draft used as the fallback when a student has no manual
 * grade form yet. Shared across the SummaryTab / GradeTableTab rows so
 * the `form` prop keeps a stable identity and React.memo can short-circuit
 * unrelated rows on every keystroke.
 *
 * Frozen so an accidental mutation surfaces immediately rather than
 * silently corrupting state for every row.
 */
export const EMPTY_FORM: Readonly<GradeForm> = Object.freeze({
  grade: "",
  comment: "",
})

/** Tiny icon (12px) that classifies a chapter in the grade table. */
export function chapterTypeIcon(type: string) {
  switch (type) {
    case "quiz":
      return <HelpCircle className="h-3 w-3" strokeWidth={1.75} />
    case "exam":
      return <GraduationCap className="h-3 w-3" strokeWidth={1.75} />
    case "assignment":
      return <ClipboardList className="h-3 w-3" strokeWidth={1.75} />
    default:
      return <FileText className="h-3 w-3" strokeWidth={1.75} />
  }
}
