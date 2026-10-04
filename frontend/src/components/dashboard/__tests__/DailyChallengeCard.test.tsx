import type { ReactNode } from "react"
import { act, render, screen, waitFor } from "@testing-library/react"
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

  it("says the question is not translated yet rather than rendering blanks", async () => {
    // Before the daily challenge was wired into the translation
    // pipeline, a reader in a language the question had not reached got
    // a 200 with empty strings: a card with no question and four blank
    // buttons. The backend now refuses to serve that, and this is what
    // the reader sees instead.
    const err = new AxiosError("not translated", "ERR_BAD_REQUEST")
    Object.assign(err, {
      response: {
        status: 404,
        data: {
          detail: {
            code: "daily_challenge.not_translated",
            message: "not translated yet",
          },
        },
      },
    })
    stub({ getToday: vi.fn().mockRejectedValue(err) })
    render(<DailyChallengeCard />, { wrapper: Wrapper })

    expect(await screen.findByText(/not in your language yet/i)).toBeInTheDocument()
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

    // With the day of the question on screen, so the answer is judged against it.
    expect(submitAttempt).toHaveBeenCalledWith("o-1", "2026-05-29")
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

  it("shows the streak before answering, unlit, and lights it once answered", async () => {
    // «Огонёк должен всегда быть показан»: outline until today's answer,
    // orange after. It used to appear only after answering.
    stub({
      getToday: vi.fn().mockResolvedValue(todayPayload()),
      getStreak: vi.fn().mockResolvedValue({ current_streak: 3, longest_streak: 5, last_engaged_date: "2026-05-28" }),
      submitAttempt: vi.fn().mockResolvedValue({
        id: "a-1",
        challenge_date: "2026-05-29",
        selected_option_id: "o-2",
        correct_option_id: "o-1",
        is_correct: false,
        explanation: "John 3:16 names the Son.",
        streak_after: 4,
        submitted_at: "2026-05-29T10:00:00Z",
      }),
    })
    render(<DailyChallengeCard />, { wrapper: Wrapper })

    const pending = await screen.findByRole("img", { name: /3/ })
    expect(pending).toHaveTextContent("3")
    expect(pending.querySelector("svg")?.getAttribute("class")).not.toContain("fill-warning")

    await userEvent.click(screen.getByText("The law"))

    const lit = await screen.findByRole("img", { name: /4/ })
    expect(lit.querySelector("svg")?.getAttribute("class")).toContain("fill-warning")
  })

  it("after a reload, shows the right answer and the explanation again", async () => {
    // The reload used to keep the chosen option and lose the rest.
    stub({
      getToday: vi.fn().mockResolvedValue(
        todayPayload({
          already_attempted: true,
          user_attempt: {
            id: "a-1",
            selected_option_id: "o-2",
            is_correct: false,
            streak_after: 4,
            submitted_at: "2026-05-29T10:00:00Z",
            correct_option_id: "o-1",
            explanation: "John 3:16 names the Son.",
          },
        }),
      ),
      getStreak: vi.fn().mockResolvedValue({ current_streak: 4, longest_streak: 5, last_engaged_date: "2026-05-29" }),
    })
    render(<DailyChallengeCard />, { wrapper: Wrapper })

    expect(await screen.findByText("John 3:16 names the Son.")).toBeInTheDocument()
    const lit = await screen.findByRole("img", { name: /4/ })
    expect(lit.querySelector("svg")?.getAttribute("class")).toContain("fill-warning")
  })

  it("drops «not in your language yet» once the language has the question", async () => {
    const err = new AxiosError("not translated", "ERR_BAD_REQUEST")
    Object.assign(err, {
      response: { status: 404, data: { detail: { code: "daily_challenge.not_translated", message: "x" } } },
    })
    const getToday = vi.fn().mockRejectedValueOnce(err).mockResolvedValue(todayPayload())
    stub({ getToday, getStreak: vi.fn().mockResolvedValue({ current_streak: 1, longest_streak: 1, last_engaged_date: null }) })
    await i18n.changeLanguage("en")
    render(<DailyChallengeCard />, { wrapper: Wrapper })
    expect(await screen.findByText(/not in your language yet/i)).toBeInTheDocument()

    await act(() => i18n.changeLanguage("ru"))

    expect(await screen.findByText(/in john 3:16, what did god give\?/i)).toBeInTheDocument()
    await act(() => i18n.changeLanguage("en"))
  })

  it("shows no streak at all, rather than «0», when the streak cannot be had", async () => {
    stub({
      getToday: vi.fn().mockResolvedValue(todayPayload()),
      getStreak: vi.fn().mockRejectedValue(new Error("offline")),
    })
    render(<DailyChallengeCard />, { wrapper: Wrapper })

    expect(await screen.findByText(/in john 3:16, what did god give\?/i)).toBeInTheDocument()
    expect(screen.queryByRole("img", { name: /0/ })).not.toBeInTheDocument()
  })
})
