import api from "./api"

export type DailyChallengeStatus =
  | "draft"
  | "scripture_validated"
  | "doctrinally_reviewed"
  | "bilingually_reviewed"
  | "pilot_passed"
  | "published"
  | "archived"

export interface AdminDailyChallengeQueueItem {
  id: string
  status: DailyChallengeStatus
  rejected: boolean
  bible_book: string
  bible_chapter: number
  bible_verse_from: number | null
  bible_verse_to: number | null
  source_locale: string | null
  has_en: boolean
  has_ru: boolean
  created_at: string
  updated_at: string
}

export interface AdminDailyChallengeQueueResponse {
  items: AdminDailyChallengeQueueItem[]
  total: number
}

export interface AdminDailyChallengeCvCell {
  cv_id: string | null
  text: string
  origin: "human" | "mt" | null
  locale: "en" | "ru"
  updated_at: string | null
}

export interface AdminDailyChallengeBilingualOption {
  id: string
  order_index: number
  is_correct: boolean
  en: AdminDailyChallengeCvCell
  ru: AdminDailyChallengeCvCell
}

export interface AdminDailyChallengeBilingualView {
  id: string
  status: DailyChallengeStatus
  rejected: boolean
  rejection_reason: string | null
  bible_book: string
  bible_chapter: number
  bible_verse_from: number | null
  bible_verse_to: number | null
  source_locale: string | null
  question_text: Record<"en" | "ru", AdminDailyChallengeCvCell>
  explanation: Record<"en" | "ru", AdminDailyChallengeCvCell>
  options: AdminDailyChallengeBilingualOption[]
}

export interface AdminDailyChallengeCvUpsertRequest {
  field: "question_text" | "explanation" | "option_text"
  locale: "en" | "ru"
  text: string
  option_id?: string
}

export interface AdminDailyChallengeQueueParams {
  status?: DailyChallengeStatus
  only_missing_ru?: boolean
  rejected?: boolean
  limit?: number
  offset?: number
}

export const adminDailyChallengeService = {
  async listQueue(params: AdminDailyChallengeQueueParams = {}): Promise<AdminDailyChallengeQueueResponse> {
    const { data } = await api.get<AdminDailyChallengeQueueResponse>(
      "/admin/daily-challenge/questions",
      { params },
    )
    return data
  },

  async getBilingualView(questionId: string): Promise<AdminDailyChallengeBilingualView> {
    const { data } = await api.get<AdminDailyChallengeBilingualView>(
      `/admin/daily-challenge/questions/${questionId}/bilingual`,
    )
    return data
  },

  async upsertCv(
    questionId: string,
    body: AdminDailyChallengeCvUpsertRequest,
  ): Promise<AdminDailyChallengeCvCell> {
    const { data } = await api.post<AdminDailyChallengeCvCell>(
      `/admin/daily-challenge/questions/${questionId}/cv`,
      body,
    )
    return data
  },

  async promote(questionId: string): Promise<void> {
    await api.post(`/admin/daily-challenge/questions/${questionId}/promote`)
  },

  async reject(questionId: string, reason: string): Promise<void> {
    await api.post(`/admin/daily-challenge/questions/${questionId}/reject`, { reason })
  },
}
