import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosError } from "axios"
import i18n from "@/i18n/config"
import { axe } from "@/test/a11y"
import { DailyChallengeCard } from "../DailyChallengeCard"
import { dailyChallengeService } from "@/services/dailyChallenge"

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </MemoryRouter>
  )
}

interface Stubs {
  getToday?: typeof dailyChallengeService.getToday
  submitAttempt?: typeof dailyChallengeService.submitAttempt
  getStreak?: typeof dailyChallengeService.getStreak
}

function stub(s: Stubs) {
  if (s.getToday) vi.spyOn(dailyChallengeService, "getToday").mockImplementation(s.getToday)
  if (s.submitAttempt)
    vi.spyOn(dailyChallengeService, "submitAttempt").mockImplementation(s.submitAttempt)
  if (s.getStreak)
    vi.spyOn(dailyChallengeService, "getStreak").mockImplementation(s.getStreak)
}

function todayPayload(overrides: Partial<Parameters<typeof Object.assign>[0]> = {}) {
  return {
    challenge_date: "2026-05-29",
    question_id: "q-1",
    question_type: "multiple_choice" as const,
    question_text: "In John 3:16, what did God give?",
    options: [
      { id: "o-1", option_text: "His only begotten Son", order_index: 0 },
      { id: "o-2", option_text: "The law", order_index: 1 },
      { id: "o-3", option_text: "Manna", order_index: 2 },
      { id: "o-4", option_text: "A new covenant", order_index: 3 },
    ],
    bible_book: "John",
    bible_book_label: "John",
    bible_chapter: 3,
    bible_verse_from: 16,
    bible_verse_to: null,
    already_attempted: false,
    user_attempt: null,
    ...overrides,
  }
}

describe("DailyChallengeCard", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("renders the question + options after load", async () => {
    stub({ getToday: vi.fn().mockResolvedValue(todayPayload()) })
    render(<DailyChallengeCard />, { wrapper: Wrapper })

    expect(
      await screen.findByText(/in john 3:16, what did god give\?/i),
    ).toBeInTheDocument()
    expect(screen.getByText("His only begotten Son")).toBeInTheDocument()
    expect(screen.getByText("A new covenant")).toBeInTheDocument()
  })

  it("renders the archive link in the header regardless of the day state", async () => {
    stub({ getToday: vi.fn().mockResolvedValue(todayPayload()) })
    render(<DailyChallengeCard />, { wrapper: Wrapper })
    // Archive link is always present so users can reach the archive
    // from the dashboard even when today has no scheduled question.
    const link = await screen.findByRole("link", { name: /archive|архив/i })
    expect(link).toHaveAttribute("href", "/daily-challenge/archive")
  })

  it("hides the question and shows an empty state on 404 not_scheduled", async () => {
    const err = new AxiosError("not scheduled", "ERR_BAD_REQUEST")
    // axios populates `response` post-construction; replicate that here.
    Object.assign(err, {
      response: {
        status: 404,
        data: {
          detail: {
            code: "daily_challenge.not_scheduled",
            message: "no schedule",
          },
        },
      },
    })
    stub({ getToday: vi.fn().mockRejectedValue(err) })
    render(<DailyChallengeCard />, { wrapper: Wrapper })

    expect(await screen.findByText(/no question today/i)).toBeInTheDocument()
  })

  it("submits a selection and reveals the correct option + streak chip", async () => {
    const getToday = vi.fn().mockResolvedValue(todayPayload())
    const submitAttempt = vi.fn().mockResolvedValue({
      id: "a-1",
      challenge_date: "2026-05-29",
      selected_option_id: "o-1",
      correct_option_id: "o-1",
      is_correct: true,
      explanation: "John 3:16 — God so loved the world.",
      streak_after: 5,
      submitted_at: "2026-05-29T12:00:00Z",
    })
    stub({ getToday, submitAttempt })

    render(<DailyChallengeCard />, { wrapper: Wrapper })

    const button = await screen.findByRole("button", { name: /his only begotten son/i })
    await userEvent.click(button)

    expect(submitAttempt).toHaveBeenCalledWith("o-1")
    expect(
      await screen.findByText(/john 3:16 — god so loved the world\./i),
    ).toBeInTheDocument()
    // Streak chip surfaces the new count with the candle/flame icon.
    expect(await screen.findByLabelText(/5-day streak/i)).toBeInTheDocument()
  })

  it("renders in reveal mode immediately when the user already attempted today", async () => {
    const getToday = vi.fn().mockResolvedValue(
      todayPayload({
        already_attempted: true,
        user_attempt: {
          id: "a-1",
          selected_option_id: "o-1",
          is_correct: true,
          streak_after: 3,
          submitted_at: "2026-05-29T12:00:00Z",
        },
      }),
    )
    const getStreak = vi.fn().mockResolvedValue({
      current_streak: 3,
      longest_streak: 10,
      last_engaged_date: "2026-05-29",
    })
    const submitAttempt = vi.fn()
    stub({ getToday, getStreak, submitAttempt })

    render(<DailyChallengeCard />, { wrapper: Wrapper })

    // Streak chip is hydrated from the streak endpoint (3 days, not the
    // stale value from the attempt snapshot).
    await waitFor(() => {
      expect(screen.getByLabelText(/3-day streak/i)).toBeInTheDocument()
    })

    // Clicking an option in reveal mode must NOT issue a submit.
    const button = screen.getByRole("button", { name: /the law/i })
    await userEvent.click(button)
    expect(submitAttempt).not.toHaveBeenCalled()
  })

  it("renders without a11y violations in the answered/reveal state", async () => {
    // The daily challenge card sits on the dashboard for every
    // logged-in student, every day. A WCAG violation here is the
    // highest-traffic regression we can ship; pin axe-clean for the
    // representative "already answered" state which renders the
    // most components (option list + streak chip + archive link).
    stub({
      getToday: vi.fn().mockResolvedValue(
        todayPayload({
          user_attempt: {
            id: "att-1",
            question_id: "q-1",
            selected_option_id: "o-1",
            is_correct: true,
            attempted_at: new Date().toISOString(),
            current_streak: 3,
          },
        }),
      ),
      getStreak: vi.fn().mockResolvedValue({
        current_streak: 3,
        longest_streak: 10,
        last_engaged_date: new Date().toISOString().slice(0, 10),
      }),
    })
    const { container } = render(<DailyChallengeCard />, { wrapper: Wrapper })
    await screen.findByLabelText(/3-day streak/i)
    expect(await axe(container)).toHaveNoViolations()
  })
})
