import React from "react"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import type { CourseTranslationProgress } from "@/services/courseTranslation"
import { CourseTranslationCard } from "@/pages/Teacher/editor/CourseTranslationCard"

/**
 * The card's one new duty: say whether anything is going to happen by
 * itself. Three states the server distinguishes and the card must too:
 *
 *   1. a job is running — the wait is ordinary and measured in minutes;
 *   2. rows are parked for a person — nothing the teacher does moves them,
 *      and somebody already knows;
 *   3. the pipeline gave up on rows — same, said differently.
 *
 * Plus the state that used to look like (1): nothing scheduled at all.
 * None of these is painted red — a stuck translation is not a fault in
 * the teacher's course.
 */

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function makeProgress(over: Partial<CourseTranslationProgress> = {}): CourseTranslationProgress {
  return {
    course_id: "c-1",
    status: "publishing",
    required: 40,
    present: 28,
    is_complete: false,
    by_locale: { de: 12 },
    gaps: { missing: 12, needs_review: 0, failed: 0 },
    held_edits: 0,
    blocked_edits: 0,
    enabled: true,
    stuck_reason: "translating",
    stuck_count: 12,
    job_pending: true,
    ...over,
  }
}

function renderCard(progress: CourseTranslationProgress, extra: Partial<React.ComponentProps<typeof CourseTranslationCard>> = {}) {
  return render(
    <CourseTranslationCard
      progress={progress}
      loading={false}
      preparing={false}
      onPrepare={() => {}}
      status="publishing"
      {...extra}
    />,
    { wrapper: Wrapper },
  )
}

describe("CourseTranslationCard — is anything going to happen?", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("says the work is running, and how long that usually takes, while a job is pending", () => {
    renderCard(makeProgress({ job_pending: true }))
    expect(screen.getByText(/Translating — 12 left/)).toBeInTheDocument()
    expect(screen.getByText(/usually takes a few minutes/)).toBeInTheDocument()
    expect(screen.queryByTestId("translation-reason")).not.toBeInTheDocument()
  })

  it("names the rows a person has to check, with the count, and says nothing is needed from the teacher", () => {
    renderCard(
      makeProgress({
        job_pending: false,
        stuck_reason: "needs_review",
        stuck_count: 3,
        gaps: { missing: 0, needs_review: 3, failed: 0 },
      }),
    )
    const reason = screen.getByTestId("translation-reason")
    expect(reason).toHaveTextContent("3 passages are waiting for a person to check them")
    expect(reason).toHaveTextContent("nothing is needed from you")
    // Not the ordinary wait: the subtitle stays on the plain count.
    expect(screen.queryByText(/Translating —/)).not.toBeInTheDocument()
  })

  it("says the rows the pipeline gave up on will be translated by hand", () => {
    renderCard(makeProgress({ job_pending: false, stuck_reason: "failed_permanent", stuck_count: 1 }))
    const reason = screen.getByTestId("translation-reason")
    expect(reason).toHaveTextContent("1 passage could not be translated automatically")
    expect(reason).toHaveTextContent("translate it by hand")
  })

  it("tells the author of a draft that translation has not started, and what starts it", () => {
    renderCard(makeProgress({ job_pending: false, stuck_reason: "translating", status: "draft" }), {
      status: "draft",
    })
    expect(screen.getByTestId("translation-reason")).toHaveTextContent(
      "Translation has not started yet",
    )
  })

  it("says a sent-out course with nothing scheduled will continue on its own", () => {
    renderCard(makeProgress({ job_pending: false, stuck_reason: "translating" }))
    expect(screen.getByTestId("translation-reason")).toHaveTextContent(
      "Translation continues on its own",
    )
  })

  it("does not paint a wait on a person red", () => {
    renderCard(makeProgress({ job_pending: false, stuck_reason: "needs_review", stuck_count: 2 }))
    expect(screen.getByTestId("translation-reason").className).not.toMatch(/destructive/)
  })

  it("offers the review queue only to somebody who can open it", () => {
    const parked = makeProgress({ job_pending: false, stuck_reason: "needs_review", stuck_count: 2 })
    const { unmount } = renderCard(parked, { reviewHref: "/admin?tab=translations&course=c-1" })
    expect(screen.getByRole("link", { name: /review queue/i })).toHaveAttribute(
      "href",
      "/admin?tab=translations&course=c-1",
    )
    unmount()
    renderCard(parked, { reviewHref: null })
    expect(screen.queryByRole("link", { name: /review queue/i })).not.toBeInTheDocument()
  })

  it("says nothing about a reason once the course is whole", () => {
    renderCard(
      makeProgress({
        is_complete: true,
        present: 40,
        by_locale: {},
        stuck_reason: null,
        stuck_count: 0,
        job_pending: false,
      }),
    )
    expect(screen.queryByTestId("translation-reason")).not.toBeInTheDocument()
    expect(screen.getByText(/exists in every language/)).toBeInTheDocument()
  })

  it("speaks Russian with the right plural, in the teacher's words", async () => {
    await i18n.changeLanguage("ru")
    renderCard(makeProgress({ job_pending: false, stuck_reason: "needs_review", stuck_count: 3 }))
    const reason = screen.getByTestId("translation-reason")
    // Cyrillic: no `\b` — JavaScript's word boundary is ASCII-only and
    // would never match. Boundaries are spelled out as letter lookarounds.
    expect(reason.textContent).toMatch(/(?<!\p{L})3 фрагмента ждут проверки человеком(?!\p{L})/u)
    expect(reason.textContent).toMatch(/с вашей стороны ничего делать не нужно/u)
    expect(reason.textContent).not.toMatch(/очеред|джоб|пайплайн/iu)
  })
})
