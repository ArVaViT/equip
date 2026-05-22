import { useCallback, useEffect, useState } from "react"
import {
  courseReadinessService,
  type ReadinessReport,
} from "@/services/courseReadiness"

interface UseCourseReadiness {
  report: ReadinessReport | null
  loading: boolean
  refresh: () => Promise<void>
}

/**
 * Fetches the readiness report for a course and exposes a refresh hook
 * so the editor can re-run the checks after each mutation (publish
 * toggle, add module, save chapter…).
 *
 * The endpoint is read-only and cheap; we refetch eagerly rather than
 * trying to maintain a local mutation diff — the report is a derived
 * view, not a source of truth.
 */
export function useCourseReadiness(courseId: string | undefined): UseCourseReadiness {
  const [report, setReport] = useState<ReadinessReport | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!courseId) return
    setLoading(true)
    try {
      const data = await courseReadinessService.get(courseId)
      setReport(data)
    } catch {
      // The card hides itself when ``report === null`` — a transient
      // backend blip shouldn't break the editor.
      setReport(null)
    } finally {
      setLoading(false)
    }
  }, [courseId])

  useEffect(() => {
    void load()
  }, [load])

  return { report, loading, refresh: load }
}
