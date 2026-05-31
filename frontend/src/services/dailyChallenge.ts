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

export interface DailyChallengeArchiveEntry {
  challenge_date: string
  question_id: string
  bible_book: string
  bible_book_label: string
  bible_chapter: number
  bible_verse_from: number | null
  bible_verse_to: number | null
  /** null = never attempted, true = correct, false = wrong */
  attempted_is_correct: boolean | null
  /** true = only archive replay (no live attempt that day) */
  archive_only_attempt: boolean
}

export interface DailyChallengeArchiveListResponse {
  entries: DailyChallengeArchiveEntry[]
  next_cursor: string | null
}

export interface DailyChallengeArchiveRevealView {
  correct_option_id: string
  explanation: string | null
  last_attempt_was_correct: boolean
}

export interface DailyChallengeArchiveQuestionResponse {
  challenge_date: string
  question_id: string
  question_type: DailyChallengeQuestionType
  question_text: string
  options: DailyChallengeOption[]
  bible_book: string
  bible_book_label: string
  bible_chapter: number
  bible_verse_from: number | null
  bible_verse_to: number | null
  reveal: DailyChallengeArchiveRevealView | null
}

export interface DailyChallengeArchiveAttemptResponse {
  id: string
  challenge_date: string
  selected_option_id: string
  correct_option_id: string
  is_correct: boolean
  explanation: string | null
  submitted_at: string
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

  async listArchive(before?: string): Promise<DailyChallengeArchiveListResponse> {
    const { data } = await api.get<DailyChallengeArchiveListResponse>(
      "/daily-challenge/archive",
      { params: before ? { before } : {} },
    )
    return data
  },

  async getArchiveQuestion(challengeDate: string): Promise<DailyChallengeArchiveQuestionResponse> {
    const { data } = await api.get<DailyChallengeArchiveQuestionResponse>(
      `/daily-challenge/archive/${challengeDate}`,
    )
    return data
  },

  async submitArchiveAttempt(
    challengeDate: string,
    selectedOptionId: string,
  ): Promise<DailyChallengeArchiveAttemptResponse> {
    const { data } = await api.post<DailyChallengeArchiveAttemptResponse>(
      `/daily-challenge/archive/${challengeDate}/attempt`,
      { selected_option_id: selectedOptionId },
    )
    return data
  },
}
