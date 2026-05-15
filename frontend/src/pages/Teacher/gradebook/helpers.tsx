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

/** Pill background/foreground tokens per letter-grade bucket. */
export function letterColor(letter: string): string {
  switch (letter) {
    case "A":
      return "bg-success/15 text-success"
    case "B":
      return "bg-info/15 text-info"
    case "C":
      return "bg-accent/20 text-foreground"
    case "D":
      return "bg-warning/15 text-warning"
    case "F":
      return "bg-destructive/15 text-destructive"
    default:
      return "bg-muted text-muted-foreground"
  }
}

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
