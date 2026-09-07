import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import { isAxiosError } from "axios"
import type {
  Quiz,
  QuizAttempt,
  QuizAnswerResult,
  QuizQuestionType,
  PendingAnswer,
} from "@/types"

type QuizCreateData = {
  chapter_id: string
  title: string
  description?: string | null
  quiz_type?: "quiz" | "exam"
  max_attempts?: number | null
  passing_score: number
  questions: Array<{
    question_text: string
    question_type: QuizQuestionType
    order_index: number
    points: number
    min_words?: number | null
    options: Array<{
      option_text: string
      is_correct: boolean
      order_index: number
    }>
  }>
}

type QuizSubmissionAnswer = {
  question_id: string
  selected_option_id?: string
  text_answer?: string
}

/** ``PUT /quizzes/{id}`` — the fields above the question list. */
export type QuizUpdateData = {
  title?: string
  description?: string | null
  quiz_type?: "quiz" | "exam"
  max_attempts?: number | null
  passing_score?: number
}

/** ``PATCH /quizzes/questions/{id}`` — one question, in place. Options
 *  are deliberately not here: they are corrected one at a time. */
export type QuizQuestionPatch = {
  question_text?: string
  question_type?: QuizQuestionType
  order_index?: number
  points?: number
  min_words?: number | null
}

/** ``PATCH /quizzes/options/{id}`` — one answer option, in place. */
export type QuizOptionPatch = {
  option_text?: string
  is_correct?: boolean
  order_index?: number
}

export const quizzesService = {
  async getChapterQuiz(chapterId: string): Promise<Quiz | null> {
    // Caches both real quizzes AND 404-as-null so chapters without a quiz
    // don't re-fetch on every render. `cached()` honours stored nulls.
    return cached(`quiz:chapter:${chapterId}`, CACHE_TTL.TWO_MINUTES, async () => {
      try {
        const response = await api.get<Quiz | null>(`/quizzes/chapter/${chapterId}`)
        return response.data
      } catch (err: unknown) {
        if (isAxiosError(err) && err.response?.status === 404) return null
        throw err
      }
    })
  },

  /**
   * Editor-only fetch: forces source-language columns (title, description,
   * question_text, option_text) regardless of the viewer's `preferred_locale`.
   * Use from `QuizEditor` / `useQuizDraft` so a teacher in EN UI editing
   * their RU quiz doesn't see EN translations in the editable fields (a
   * PATCH would then overwrite the source `question_text` column).
   *
   * Owner / admin only — the backend returns 403 for anyone else.
   * Intentionally bypasses the `quiz:chapter:{id}` cache so a teacher
   * switching between taking and editing the same quiz doesn't see one
   * view's payload bleed into the other.
   */
  async getChapterQuizForEdit(chapterId: string): Promise<Quiz | null> {
    try {
      const response = await api.get<Quiz | null>(
        `/quizzes/chapter/${chapterId}`,
        { params: { source: 1 } },
      )
      return response.data
    } catch (err: unknown) {
      if (isAxiosError(err) && err.response?.status === 404) {
        return null
      }
      throw err
    }
  },

  async createQuiz(data: QuizCreateData): Promise<Quiz> {
    const response = await api.post<Quiz>("/quizzes", data)
    cacheInvalidate(`quiz:chapter:${data.chapter_id}`)
    return response.data
  },

  /**
   * Delete a quiz. Refused with 409 ``quiz.has_attempts`` once students
   * have attempted it — every attempt and grade goes with the quiz — unless
   * ``force`` is passed, which a caller does only after showing the teacher
   * the number and hearing yes.
   */
  async deleteQuiz(quizId: string, chapterId?: string, opts: { force?: boolean } = {}): Promise<void> {
    await api.delete(`/quizzes/${quizId}`, opts.force ? { params: { force: true } } : undefined)
    if (chapterId) {
      cacheInvalidate(`quiz:chapter:${chapterId}`)
    } else {
      cacheInvalidatePrefix("quiz:chapter:")
    }
  },

  /**
   * The in-place routes: a correction to a quiz a class has already taken
   * keeps every attempt on it. Each returns the whole quiz, re-read.
   */
  async updateQuiz(quizId: string, data: QuizUpdateData, chapterId: string): Promise<Quiz> {
    const response = await api.put<Quiz>(`/quizzes/${quizId}`, data)
    cacheInvalidate(`quiz:chapter:${chapterId}`)
    return response.data
  },

  async updateQuizQuestion(questionId: string, patch: QuizQuestionPatch, chapterId: string): Promise<Quiz> {
    const response = await api.patch<Quiz>(`/quizzes/questions/${questionId}`, patch)
    cacheInvalidate(`quiz:chapter:${chapterId}`)
    return response.data
  },

  async updateQuizOption(optionId: string, patch: QuizOptionPatch, chapterId: string): Promise<Quiz> {
    const response = await api.patch<Quiz>(`/quizzes/options/${optionId}`, patch)
    cacheInvalidate(`quiz:chapter:${chapterId}`)
    return response.data
  },

  /** Every attempt on a quiz — the teacher's view. Up to the API's cap. */
  async getQuizAttempts(quizId: string): Promise<QuizAttempt[]> {
    const response = await api.get<QuizAttempt[]>(`/quizzes/${quizId}/attempts`, { params: { limit: 500 } })
    return response.data
  },

  async submitQuiz(quizId: string, answers: QuizSubmissionAnswer[]): Promise<QuizAttempt> {
    const response = await api.post<QuizAttempt>(`/quizzes/${quizId}/submit`, { answers })
    cacheInvalidatePrefix("progress:my:")
    return response.data
  },

  async getMyQuizAttempts(quizId: string): Promise<QuizAttempt[]> {
    const response = await api.get<QuizAttempt[]>(`/quizzes/${quizId}/my-attempts`)
    return response.data
  },

  async getPendingAnswers(quizId: string, includeGraded = false): Promise<PendingAnswer[]> {
    const response = await api.get<PendingAnswer[]>(
      `/quizzes/${quizId}/pending-answers`,
      { params: { include_graded: includeGraded } },
    )
    return response.data
  },

  async gradeQuizAnswer(
    answerId: string,
    pointsEarned: number,
    graderComment?: string | null,
  ): Promise<QuizAnswerResult> {
    const response = await api.patch<QuizAnswerResult>(`/quizzes/answers/${answerId}`, {
      points_earned: pointsEarned,
      grader_comment: graderComment ?? null,
    })
    // Grading an essay/short-answer changes the same aggregates assignment
    // grading does — keep the invalidation set in sync with gradeSubmission
    // (assignments.ts), or stale gradebook/progress values survive up to 30s.
    cacheInvalidatePrefix("grades:course:")
    cacheInvalidatePrefix("grades:summary:")
    cacheInvalidatePrefix("grades:my")
    cacheInvalidatePrefix("analytics:course:")
    cacheInvalidatePrefix("progress:students:")
    cacheInvalidatePrefix("progress:gradebook:")
    cacheInvalidatePrefix("progress:detail:")
    return response.data
  },

  async grantExtraAttempts(
    quizId: string,
    userId: string,
    extraAttempts: number,
  ): Promise<void> {
    await api.post(`/quizzes/${quizId}/extra-attempts`, {
      user_id: userId,
      extra_attempts: extraAttempts,
    })
  },
}
