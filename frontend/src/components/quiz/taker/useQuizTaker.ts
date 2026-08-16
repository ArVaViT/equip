import { useEffect, useState } from "react"
import { getErrorCode } from "@/lib/errorCode"
import { coursesService } from "@/services/courses"
import type { Quiz, QuizAttempt } from "@/types"

interface Params {
  chapterId: string
  quizId?: string
}

interface UseQuizTakerResult {
  loading: boolean
  fetchError: boolean
  /** The quiz exists, but not in this reader's language. A wait, not a failure. */
  notTranslated: boolean
  quiz: Quiz | null
  /** `null` when the attempts request failed. Not an empty history. */
  attempts: QuizAttempt[] | null
  setAttempts: React.Dispatch<React.SetStateAction<QuizAttempt[] | null>>
}

export function useQuizTaker({ chapterId, quizId }: Params): UseQuizTakerResult {
  const [quiz, setQuiz] = useState<Quiz | null>(null)
  // Starts `null` — before the fetch lands we have not found out either.
  const [attempts, setAttempts] = useState<QuizAttempt[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [notTranslated, setNotTranslated] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFetchError(false)
    setNotTranslated(false)
    setAttempts([])
    setQuiz(null)

    const load = async () => {
      try {
        const [q, preloadedAttempts] = quizId
          ? await Promise.all([
              coursesService.getChapterQuiz(chapterId),
              // `null`, not `[]` — see `attemptGate`. An empty list means the
              // student has sat this quiz none times; a failed request means we
              // do not know, and the two must not open the same door.
              coursesService.getMyQuizAttempts(quizId).catch(() => null),
            ])
          : [await coursesService.getChapterQuiz(chapterId), null]
        if (cancelled) return
        const resolved = quizId && q && q.id !== quizId ? null : q
        setQuiz(resolved)
        if (resolved) {
          const att =
            preloadedAttempts ??
            (await coursesService.getMyQuizAttempts(resolved.id).catch(() => null))
          if (!cancelled) setAttempts(att)
        }
      } catch (err: unknown) {
        if (cancelled) return
        // A quiz that exists but not in this reader's language. The
        // backend refuses rather than handing over blank questions on a
        // graded attempt; this is a wait, not a failure, and it reads
        // differently to the student.
        if (getErrorCode(err) === "quiz.not_translated") setNotTranslated(true)
        else setFetchError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [chapterId, quizId])

  return { loading, fetchError, notTranslated, quiz, attempts, setAttempts }
}
