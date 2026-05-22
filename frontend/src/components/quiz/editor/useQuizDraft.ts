import { useCallback, useEffect, useState } from "react"
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
}

interface UseQuizDraftResult {
  loading: boolean
  existingQuiz: Quiz | null
  setExistingQuiz: (q: Quiz | null) => void
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
}

const defaultMaxAttempts = (chapterType: "quiz" | "exam") =>
  chapterType === "exam" ? 1 : 3

export function useQuizDraft({
  chapterId,
  chapterType,
}: Params): UseQuizDraftResult {
  const [existingQuiz, setExistingQuiz] = useState<Quiz | null>(null)
  const [loading, setLoading] = useState(true)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [passingScore, setPassingScore] = useState(70)
  const [maxAttempts, setMaxAttempts] = useState<number>(1)
  const [questions, setQuestions] = useState<DraftQuestion[]>([])

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
        } else {
          setMaxAttempts(defaultMaxAttempts(chapterType))
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
  }, [chapterId, chapterType])

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

  const resetAll = useCallback(() => {
    setExistingQuiz(null)
    setTitle("")
    setDescription("")
    setPassingScore(70)
    setMaxAttempts(defaultMaxAttempts(chapterType))
    setQuestions([])
  }, [chapterType])

  return {
    loading,
    existingQuiz,
    setExistingQuiz,
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
