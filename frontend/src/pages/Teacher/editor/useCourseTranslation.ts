import { useCallback, useEffect, useRef, useState } from "react"

import {
  courseTranslationService,
  type CourseTranslationProgress,
} from "@/services/courseTranslation"

interface UseCourseTranslation {
  progress: CourseTranslationProgress | null
  loading: boolean
  preparing: boolean
  /** Kick off a full pass and start watching it. */
  prepare: () => Promise<void>
  refresh: () => Promise<void>
}

/**
 * How long to wait between progress checks while work is in flight.
 *
 * The worker claims one job per cron minute, so anything faster than
 * this is asking a question whose answer cannot have changed. Slower and
 * a short course looks stuck when it is already done.
 */
const POLL_MS = 15_000

/**
 * Watches a course's translation state for the editor.
 *
 * Polls only while there is something to watch — work outstanding or an
 * edit still being held — and stops as soon as the course is whole. An
 * editor left open on a finished course costs nothing.
 */
export function useCourseTranslation(courseId: string | undefined): UseCourseTranslation {
  const [progress, setProgress] = useState<CourseTranslationProgress | null>(null)
  const [loading, setLoading] = useState(true)
  const [preparing, setPreparing] = useState(false)
  // Held in a ref as well as state so the interval callback reads the
  // current value instead of the one captured when it was scheduled.
  const inFlight = useRef(false)

  const load = useCallback(async () => {
    if (!courseId) return
    try {
      const data = await courseTranslationService.progress(courseId)
      setProgress(data)
      inFlight.current = !data.is_complete || data.held_edits > 0
    } catch {
      // The panel hides itself on null. A transient failure must not
      // take the editor down with it.
      setProgress(null)
      inFlight.current = false
    } finally {
      setLoading(false)
    }
  }, [courseId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!courseId) return
    const id = window.setInterval(() => {
      // Nothing outstanding: stop asking. The panel is still on screen,
      // it just has nothing left to report.
      if (!inFlight.current) return
      void load()
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [courseId, load])

  const prepare = useCallback(async () => {
    if (!courseId) return
    setPreparing(true)
    try {
      await courseTranslationService.prepare(courseId)
      // Read straight back so the panel switches from "not started" to
      // "in progress" on the same click rather than at the next tick.
      await load()
      inFlight.current = true
    } finally {
      setPreparing(false)
    }
  }, [courseId, load])

  return { progress, loading, preparing, prepare, refresh: load }
}
