import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { gradesService } from "@/services/grades"
import { GradeHistory } from "../GradeHistory"
import type { GradeHistoryEntry } from "@/types"

function entry(over: Partial<GradeHistoryEntry> = {}): GradeHistoryEntry {
  return {
    id: "a-1",
    action: "grade_override_set",
    at: "2026-08-10T09:00:00Z",
    actor_id: "t-1",
    actor_name: "Мария Петровна",
    override_code: "B",
    override_score: null,
    computed_score: "64.00",
    reason: "Сдавал устно, письменная работа утеряна",
    item_type: null,
    item_id: null,
    blockers: [],
    ...over,
  }
}

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

async function open(entries: GradeHistoryEntry[]) {
  vi.spyOn(gradesService, "getGradeHistory").mockResolvedValue(entries)
  render(<GradeHistory courseId="c-1" studentId="s-1" />, { wrapper: Wrapper })
  await userEvent.click(screen.getByRole("button"))
}

describe("GradeHistory", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("does not ask the server until somebody asks it to", () => {
    const load = vi.spyOn(gradesService, "getGradeHistory").mockResolvedValue([])
    render(<GradeHistory courseId="c-1" studentId="s-1" />, { wrapper: Wrapper })

    // Most students never have a history. Paying for the query on every row
    // expansion to render "nothing happened" is how a board gets slow.
    expect(load).not.toHaveBeenCalled()
  })

  it("says who set the grade, what it was, and what the system had computed", async () => {
    await open([entry()])

    expect(await screen.findByText(/Оценка выставлена вручную: B/)).toBeInTheDocument()
    // "Teacher set B" says little. "Teacher set B where the system computed
    // 64%" is the sentence a director actually needs.
    expect(screen.getByText(/система считала 64.00%/)).toBeInTheDocument()
    expect(screen.getByText(/Мария Петровна/)).toBeInTheDocument()
  })

  it("shows the reason, which is the whole point of keeping it", async () => {
    await open([entry()])

    expect(await screen.findByText(/письменная работа утеряна/)).toBeInTheDocument()
  })

  it("says plainly when nothing was ever set by hand", async () => {
    await open([])

    expect(await screen.findByText(/Оценку вручную не меняли/)).toBeInTheDocument()
  })

  it("offers another go when the request fails", async () => {
    vi.spyOn(gradesService, "getGradeHistory").mockRejectedValue(new Error("nope"))
    render(<GradeHistory courseId="c-1" studentId="s-1" />, { wrapper: Wrapper })

    await userEvent.click(screen.getByRole("button"))

    // Silence here reads as "no history", which is a different fact.
    expect(await screen.findByRole("button", { name: /ещё раз/ })).toBeInTheDocument()
  })

  it("names an action it has no words for without printing the key", async () => {
    await open([entry({ action: "some_future_action", override_code: null, computed_score: null })])

    expect(await screen.findByText(/Изменение оценки/)).toBeInTheDocument()
    expect(screen.queryByText(/some_future_action/)).not.toBeInTheDocument()
  })

  it("drops the previous student's history when the drawer moves", async () => {
    vi.spyOn(gradesService, "getGradeHistory").mockResolvedValue([entry()])
    const { rerender } = render(<GradeHistory courseId="c-1" studentId="s-1" />, { wrapper: Wrapper })
    await userEvent.click(screen.getByRole("button"))
    expect(await screen.findByText(/Мария Петровна/)).toBeInTheDocument()

    rerender(<GradeHistory courseId="c-1" studentId="s-2" />)

    // Showing one student's hand-set grade under another's name is the worst
    // available failure on a screen about who did what to whose grade.
    expect(screen.queryByText(/Мария Петровна/)).not.toBeInTheDocument()
    expect(screen.getByRole("button")).toBeInTheDocument()
  })
})
