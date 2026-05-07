import type { Cohort } from "@/types"
import { formatDate as formatDateI18n } from "@/i18n/format"

export interface CourseMaterial {
  name: string
  path: string
  size?: number
  created: string | null
}

type CohortEnrollmentStatus = "not_started" | "closed" | "open" | "no_window"

export function formatDate(dateStr: string): string {
  return formatDateI18n(dateStr, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function getCohortEnrollmentStatus(cohort: Cohort): CohortEnrollmentStatus {
  const now = new Date()
  const start = cohort.enrollment_start ? new Date(cohort.enrollment_start) : null
  const end = cohort.enrollment_end ? new Date(cohort.enrollment_end) : null
  if (start && now < start) return "not_started"
  if (end && now > end) return "closed"
  if (start || end) return "open"
  return "no_window"
}

export function isEnrollableCohort(cohort: Cohort): boolean {
  return (
    (cohort.status === "active" || cohort.status === "upcoming") &&
    getCohortEnrollmentStatus(cohort) === "open"
  )
}
