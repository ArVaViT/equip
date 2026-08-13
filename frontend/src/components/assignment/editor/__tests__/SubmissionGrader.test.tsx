import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { rubricsService } from "@/services/rubrics"
import { SubmissionGrader } from "../SubmissionGrader"
import type { AssignmentSubmission, SubmissionRubric } from "@/types"

const SUBMISSION: AssignmentSubmission = {
  id: "sub-1",
  assignment_id: "a-1",
  student_id: "student-1",
  content: "Работа",
  file_url: null,
  submitted_at: "2026-08-12T09:00:00Z",
  status: "submitted",
  // Not marked yet — which is exactly the state the bug needed.
  grade: null,
  feedback: null,
} as AssignmentSubmission

const WITH_RUBRIC: SubmissionRubric = {
  rubric: {
    id: "r-1",
    course_id: "c-1",
    title: "Эссе",
    max_score: 100,
    criteria: [
      {
        id: "cr-1",
        title: "Опора на текст",
        description: null,
        order_index: 0,
        levels: [
          { id: "l-1", label: "нет", points: 0, description: null, order_index: 0 },
          { id: "l-2", label: "да", points: 82, description: null, order_index: 1 },
        ],
      },
    ],
  },
  marks: [{ criterion_id: "cr-1", level_id: "l-2", points: 82, comment: null }],
  earned: 82,
  out_of: 100,
}

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("SubmissionGrader — the number belongs to whoever owns it", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("never writes a grade of its own when a rubric decides the mark", async () => {
    // The bug this exists for, shipped in #969: the number field is hidden
    // when a rubric is attached, so `grade` state stayed at its initial
    // `submission.grade ?? 0`. Marking through the grid wrote 82 on the
    // server; pressing Save then wrote **0** over it and said «Проверено».
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue(WITH_RUBRIC)
    const setMarks = vi.spyOn(rubricsService, "setMarks").mockResolvedValue(WITH_RUBRIC)
    const gradeSubmission = vi.spyOn(coursesService, "gradeSubmission")

    render(<SubmissionGrader submission={SUBMISSION} maxScore={100} onUpdate={vi.fn()} />, {
      wrapper: Wrapper,
    })
    await screen.findByText("Опора на текст")
    await userEvent.click(screen.getByRole("button", { name: /Сохранить/i }))

    await waitFor(() => expect(setMarks).toHaveBeenCalled())
    expect(gradeSubmission).not.toHaveBeenCalled()
    // And the levels it re-sends are the ones already chosen, so the note is
    // carried without touching the mark.
    expect(setMarks.mock.calls[0]?.[1]).toEqual([{ criterion_id: "cr-1", level_id: "l-2" }])
  })

  it("still writes the typed number when there is no rubric", async () => {
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({
      rubric: null,
      marks: [],
      earned: null,
      out_of: null,
    })
    const gradeSubmission = vi
      .spyOn(coursesService, "gradeSubmission")
      .mockResolvedValue(SUBMISSION)

    render(<SubmissionGrader submission={SUBMISSION} maxScore={100} onUpdate={vi.fn()} />, {
      wrapper: Wrapper,
    })
    await userEvent.click(screen.getByRole("button", { name: /Сохранить/i }))

    await waitFor(() => expect(gradeSubmission).toHaveBeenCalled())
  })
})
