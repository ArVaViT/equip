import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { StudentRow } from "../StudentRow"
import type { StudentData } from "../helpers"
import type { RetakeRequest } from "@/types"

function makeStudent(): StudentData {
  return {
    id: "s-1",
    full_name: "Пётр Иванов",
    email: "petr@example.com",
    progress: 100,
    chapters_completed: 4,
    total_chapters: 4,
    quiz_avg: 40,
    assignment_avg: 45,
    last_activity: "2026-08-01T10:00:00Z",
    enrolled_at: "2026-06-01T10:00:00Z",
    overall_grade: 42,
    current_grade: 42,
    current_letter_grade: "F",
    scores_differ: false,
    manual_grade: null,
    result_state: "graded",
    letter_grade: "F",
  }
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <table>
          <tbody>{children}</tbody>
        </table>
      </MemoryRouter>
    </I18nextProvider>
  )
}

function show(retakeRequest?: RetakeRequest, { expanded = false } = {}) {
  return render(
    <StudentRow
      student={makeStudent()}
      retakeRequest={retakeRequest}
      isExpanded={expanded}
      onToggle={vi.fn()}
      quizAvg={40}
      assignmentAvg={45}
      courseId="c-1"
      onChapterUpdate={vi.fn()}
    />,
    { wrapper: Wrapper },
  )
}

describe("StudentRow — a student who asked for a way forward", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })

  it("marks the row, so the request outlives the notification", () => {
    show({ student_id: "s-1", requested_at: "2026-08-10T09:00:00Z", blockers: ["below_threshold"] })

    // A notification is read once and gone. A student who asked in week three
    // and was missed has no way to raise it again and no evidence they did.
    expect(screen.getByText(/просит пересдачу/)).toBeInTheDocument()
  })

  it("says what stopped them, so the teacher knows which power this calls for", () => {
    show(
      { student_id: "s-1", requested_at: null, blockers: ["quizzes_not_passed"] },
      { expanded: true },
    )

    expect(screen.getByText(/тест не пройден/)).toBeInTheDocument()
  })

  it("marks nothing when nobody asked", () => {
    show(undefined)

    expect(screen.queryByText(/просит пересдачу/)).not.toBeInTheDocument()
  })

  it("still says a student asked when the reason is a code this build has no words for", () => {
    show({ student_id: "s-1", requested_at: null, blockers: ["some_future_rule"] }, { expanded: true })

    // Both the row marker and the expanded panel say it; either alone is enough.
    expect(screen.getAllByText(/просит пересдачу/i).length).toBeGreaterThan(0)
    // Rather than a raw translation key next to somebody's name.
    expect(screen.queryByText(/some_future_rule/)).not.toBeInTheDocument()
    expect(screen.getByText(/Причина не сохранилась/)).toBeInTheDocument()
  })
})
