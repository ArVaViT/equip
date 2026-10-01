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

export interface ReviewWaiting {
  course_id: string
  course_title: string | null
  count: number
}

/** The week's review: practice only, nothing written, nothing graded. */
export const reviewService = {
  /** Which of the reader's courses have a review this week — for the home page. */
  async waiting(): Promise<ReviewWaiting[]> {
    return (await api.get<ReviewWaiting[]>("/review/me")).data
  },
  async forCourse(courseId: string): Promise<ReviewQuestion[]> {
    return (await api.get<ReviewQuestion[]>(`/review/course/${encodeURIComponent(courseId)}`)).data
  },
  async check(questionId: string, optionId: string): Promise<ReviewVerdict> {
    return (await api.post<ReviewVerdict>("/review/check", { question_id: questionId, option_id: optionId })).data
  },
}
