import { useCallback, useEffect, useRef, useState } from "react"
import { coursesService } from "@/services/courses"
import type { Quiz } from "@/types"
import {
  makeDefaultOption,
  makeDefaultQuestion,
  makeTrueFalseOptions,
  type DraftOption,
  type DraftQuestion,
} from "./types"

interface Params {
  chapterId: string
  chapterType: "quiz" | "exam"
  /** A new quiz starts with the lesson's name, not an empty required
   *  field the teacher has to fill with the same words again. */
  defaultTitle?: string
}

interface UseQuizDraftResult {
  loading: boolean
  existingQuiz: Quiz | null
  setExistingQuiz: (q: Quiz | null) => void
  /** How many attempts students have made on ``existingQuiz`` — what a
   *  rebuild would delete. 0 when there is no quiz or the count failed
   *  to load (the server refuses the delete either way). */
  attemptCount: number
  /** Questions at least one student has answered: their type is fixed. */
  answeredQuestionIds: ReadonlySet<string>
  /** After a rebuild: the new quiz has no attempts yet. */
  clearAttempts: () => void
  /** Show this quiz, replacing whatever was on screen: the editor found
   *  out the server's quiz is not the one it was editing (the lesson
   *  already had one; somebody rebuilt it meanwhile). */
  adoptQuiz: (q: Quiz) => void
  title: string
  setTitle: (v: string) => void
  description: string
  setDescription: (v: string) => void
  passingScore: number
  setPassingScore: (v: number) => void
  maxAttempts: number
  setMaxAttempts: (v: number) => void
  questions: DraftQuestion[]
  setQuestions: React.Dispatch<React.SetStateAction<DraftQuestion[]>>
  addQuestion: () => void
  removeQuestion: (idx: number) => void
  moveQuestion: (idx: number, direction: "up" | "down") => void
  updateQuestion: (idx: number, patch: Partial<DraftQuestion>) => void
  addOption: (qIdx: number) => void
  removeOption: (qIdx: number, oIdx: number) => void
  updateOption: (qIdx: number, oIdx: number, patch: Partial<DraftOption>) => void
  resetAll: () => void
  /** Something typed here is not on the server yet. Compared against the
   *  draft as it was loaded or last saved, so undoing a change clears it. */
  isDirty: boolean
  /** The draft on screen is now what the server holds. */
  /** The draft as it now stands, in the form `markSaved` takes. */
  snapshotKey: string
  markSaved: (sent?: string) => void
}

const defaultMaxAttempts = (chapterType: "quiz" | "exam") =>
  chapterType === "exam" ? 1 : 3

export function useQuizDraft({
  chapterId,
  chapterType,
  defaultTitle = "",
}: Params): UseQuizDraftResult {
  // Read when a lesson opens, not followed: renaming the lesson must not
  // reload a quiz that is being written.
  const defaultTitleRef = useRef(defaultTitle)
  useEffect(() => {
    defaultTitleRef.current = defaultTitle
  }, [defaultTitle])
  const [existingQuiz, setExistingQuiz] = useState<Quiz | null>(null)
  const [loading, setLoading] = useState(true)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [passingScore, setPassingScore] = useState(70)
  const [maxAttempts, setMaxAttempts] = useState<number>(1)
  const [questions, setQuestions] = useState<DraftQuestion[]>([])
  const [attemptCount, setAttemptCount] = useState(0)
  const [answeredQuestionIds, setAnsweredQuestionIds] = useState<ReadonlySet<string>>(() => new Set())

  const adoptQuiz = useCallback((q: Quiz) => {
    setExistingQuiz(q)
    setTitle(q.title)
    setDescription(q.description ?? "")
    setPassingScore(q.passing_score)
    setMaxAttempts(q.max_attempts ?? 1)
    setQuestions(
      q.questions
        .sort((a, b) => a.order_index - b.order_index)
        .map((qu) => ({
          ...qu,
          min_words: qu.min_words ?? null,
          options: qu.options
            .sort((a, b) => a.order_index - b.order_index)
            .map((o) => ({ ...o, is_correct: !!o.is_correct })),
        })),
    )
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        // Editor-only fetch so the form binds to source-language
        // `question_text` / `option_text` columns regardless of UI locale.
        // Without this a teacher in EN UI editing their RU quiz would
        // see EN translations in the question editor and a PATCH would
        // overwrite the source `question_text`.
        const q = await coursesService.getChapterQuizForEdit(chapterId)
        if (cancelled) return
        if (q) {
          adoptQuiz(q)
          // What a rebuild would cost. Best-effort: if this fails the
          // editor still opens, the count reads 0, and the server's own
          // 409 is the backstop — it never deletes attempts unasked.
          try {
            const attempts = await coursesService.getQuizAttempts(q.id)
            if (cancelled) return
            setAttemptCount(attempts.length)
            setAnsweredQuestionIds(
              new Set(attempts.flatMap((attempt) => (attempt.answers ?? []).map((a) => a.question_id))),
            )
          } catch {
            if (!cancelled) {
              setAttemptCount(0)
              setAnsweredQuestionIds(new Set())
            }
          }
        } else {
          setMaxAttempts(defaultMaxAttempts(chapterType))
          setTitle(defaultTitleRef.current)
        }
      } catch {
        if (!cancelled) setQuestions([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [chapterId, chapterType, adoptQuiz])

  const addQuestion = useCallback(() => {
    setQuestions((prev) => [...prev, makeDefaultQuestion(prev.length)])
  }, [])

  const removeQuestion = useCallback((idx: number) => {
    setQuestions((prev) =>
      prev.filter((_, i) => i !== idx).map((q, i) => ({ ...q, order_index: i })),
    )
  }, [])

  const moveQuestion = useCallback((idx: number, direction: "up" | "down") => {
    setQuestions((prev) => {
      const next = [...prev]
      const targetIdx = direction === "up" ? idx - 1 : idx + 1
      if (targetIdx < 0 || targetIdx >= next.length) return prev
      const a = next[idx]
      const b = next[targetIdx]
      if (!a || !b) return prev
      next[idx] = b
      next[targetIdx] = a
      return next.map((q, i) => ({ ...q, order_index: i }))
    })
  }, [])

  const updateQuestion = useCallback(
    (idx: number, patch: Partial<DraftQuestion>) => {
      setQuestions((prev) =>
        prev.map((q, i) => {
          if (i !== idx) return q
          const updated = { ...q, ...patch }
          if (patch.question_type && patch.question_type !== q.question_type) {
            if (patch.question_type === "true_false") {
              updated.options = makeTrueFalseOptions()
            } else if (
              patch.question_type === "short_answer" ||
              patch.question_type === "essay"
            ) {
              updated.options = []
            } else {
              updated.options = [makeDefaultOption(0), makeDefaultOption(1)]
            }
            // ``min_words`` only makes sense for ``essay``; clear it when the
            // teacher switches away so a stale hint doesn't linger on e.g. MCQ.
            if (patch.question_type !== "essay") {
              updated.min_words = null
            }
          }
          return updated
        }),
      )
    },
    [],
  )

  const addOption = useCallback((qIdx: number) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i === qIdx
          ? { ...q, options: [...q.options, makeDefaultOption(q.options.length)] }
          : q,
      ),
    )
  }, [])

  const removeOption = useCallback((qIdx: number, oIdx: number) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i === qIdx
          ? {
              ...q,
              options: q.options
                .filter((_, j) => j !== oIdx)
                .map((o, j) => ({ ...o, order_index: j })),
            }
          : q,
      ),
    )
  }, [])

  const updateOption = useCallback(
    (qIdx: number, oIdx: number, patch: Partial<DraftOption>) => {
      setQuestions((prev) =>
        prev.map((q, i) =>
          i === qIdx
            ? {
                ...q,
                options: q.options.map((o, j) => {
                  if (j !== oIdx) {
                    if (patch.is_correct) return { ...o, is_correct: false }
                    return o
                  }
                  return { ...o, ...patch }
                }),
              }
            : q,
        ),
      )
    },
    [],
  )

  const clearAttempts = useCallback(() => {
    setAttemptCount(0)
    setAnsweredQuestionIds(new Set())
  }, [])

  const resetAll = useCallback(() => {
    setExistingQuiz(null)
    setTitle("")
    setDescription("")
    setPassingScore(70)
    setMaxAttempts(defaultMaxAttempts(chapterType))
    setQuestions([])
    clearAttempts()
  }, [chapterType, clearAttempts])

  // The saved state, as the same string the draft is compared in. `null`
  // while loading; taken from the first render after the load finishes,
  // and again after every save (`markSaved`).
  const current = JSON.stringify({ title, description, passingScore, maxAttempts, questions })
  const [baseline, setBaseline] = useState<string | null>(null)
  const [saveMarked, setSaveMarked] = useState(false)
  useEffect(() => {
    if (loading) {
      setBaseline(null)
      return
    }
    if (baseline === null || saveMarked) {
      setBaseline(current)
      setSaveMarked(false)
    }
  }, [loading, baseline, saveMarked, current])
  // With `sent` — the draft as it was when the save went out — edits made
  // while the request was in flight stay unsaved, as they are. Without it,
  // the next render's draft becomes the baseline (after a delete, or a
  // rebuild that sets fields from the server's answer).
  const markSaved = useCallback((sent?: string) => {
    if (sent === undefined) setSaveMarked(true)
    else setBaseline(sent)
  }, [])
  const isDirty = !loading && baseline !== null && !saveMarked && current !== baseline

  return {
    loading,
    isDirty,
    snapshotKey: current,
    markSaved,
    existingQuiz,
    setExistingQuiz,
    attemptCount,
    answeredQuestionIds,
    clearAttempts,
    adoptQuiz,
    title,
    setTitle,
    description,
    setDescription,
    passingScore,
    setPassingScore,
    maxAttempts,
    setMaxAttempts,
    questions,
    setQuestions,
    addQuestion,
    removeQuestion,
    moveQuestion,
    updateQuestion,
    addOption,
    removeOption,
    updateOption,
    resetAll,
  }
}
