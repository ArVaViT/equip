import api from "./api"

export interface ReviewQuestion {
  id: string
  question_text: string
  options: { id: string; option_text: string }[]
}

export interface ReviewVerdict {
  correct: boolean
  correct_option_id: string
}

/** The week's review: practice only, nothing written, nothing graded. */
export const reviewService = {
  async forCourse(courseId: string): Promise<ReviewQuestion[]> {
    return (await api.get<ReviewQuestion[]>(`/review/course/${encodeURIComponent(courseId)}`)).data
  },
  async check(questionId: string, optionId: string): Promise<ReviewVerdict> {
    return (await api.post<ReviewVerdict>("/review/check", { question_id: questionId, option_id: optionId })).data
  },
}
