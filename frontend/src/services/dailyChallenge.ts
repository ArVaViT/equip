import api from "./api"

export type DailyChallengeQuestionType = "multiple_choice" | "true_false"

export interface DailyChallengeOption {
  id: string
  option_text: string
  order_index: number
}

export interface DailyChallengeAttemptSummary {
  id: string
  selected_option_id: string
  is_correct: boolean
  streak_after: number
  submitted_at: string
}

export interface DailyChallengeTodayResponse {
  challenge_date: string
  question_id: string
  question_type: DailyChallengeQuestionType
  question_text: string
  options: DailyChallengeOption[]
  bible_book: string
  /** Localized short-form book label (e.g. "Ин." for ru, "John" for en). */
  bible_book_label: string
  bible_chapter: number
  bible_verse_from: number | null
  bible_verse_to: number | null
  already_attempted: boolean
  user_attempt: DailyChallengeAttemptSummary | null
}

export interface DailyChallengeAttemptResponse {
  id: string
  challenge_date: string
  selected_option_id: string
  correct_option_id: string
  is_correct: boolean
  explanation: string | null
  streak_after: number
  submitted_at: string
}

export interface DailyChallengeStreakResponse {
  current_streak: number
  longest_streak: number
  last_engaged_date: string | null
}

/**
 * One question per UTC day for every user; platform-wide schedule.
 * The dashboard card hides itself on 404 (the
 * ``daily_challenge.not_scheduled`` error envelope) so an off-schedule
 * day doesn't show a broken-feeling empty rectangle.
 */
export const dailyChallengeService = {
  async getToday(): Promise<DailyChallengeTodayResponse> {
    const { data } = await api.get<DailyChallengeTodayResponse>("/daily-challenge/today")
    return data
  },

  async submitAttempt(selectedOptionId: string): Promise<DailyChallengeAttemptResponse> {
    const { data } = await api.post<DailyChallengeAttemptResponse>(
      "/daily-challenge/today/attempt",
      { selected_option_id: selectedOptionId },
    )
    return data
  },

  async getStreak(): Promise<DailyChallengeStreakResponse> {
    const { data } = await api.get<DailyChallengeStreakResponse>("/daily-challenge/streak")
    return data
  },
}
