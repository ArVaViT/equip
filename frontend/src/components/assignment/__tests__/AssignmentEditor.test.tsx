import React from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"

const getChapterAssignmentsForEdit = vi.fn()
vi.mock("@/services/courses", () => ({
  coursesService: {
    getChapterAssignmentsForEdit: (...a: unknown[]) => getChapterAssignmentsForEdit(...a),
    createAssignment: vi.fn(),
    deleteAssignment: vi.fn(),
  },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
vi.mock("@/components/ui/alert-dialog", () => ({ useConfirm: () => vi.fn().mockResolvedValue(true) }))

import AssignmentEditor from "../AssignmentEditor"

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

/**
 * «New assignment» doubled as a close button while the form was open, so a
 * second click dropped what the teacher had typed without a word
 * (2026-09-29). It shows only when the form is closed now.
 */
describe("the new-assignment button", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
  })
  beforeEach(() => {
    vi.clearAllMocks()
    getChapterAssignmentsForEdit.mockResolvedValue([])
  })

  it("is not there while the form is open, so it cannot close it", async () => {
    render(<AssignmentEditor chapterId="ch-1" courseId="c-1" defaultTitle="Эссе" />, { wrapper: Wrapper })
    // An assignment lesson with nothing in it opens the form at once.
    await screen.findByDisplayValue("Эссе")
    expect(screen.queryByRole("button", { name: "Новое задание" })).not.toBeInTheDocument()
  })

  it("comes back once the form is cancelled", async () => {
    const user = userEvent.setup()
    render(<AssignmentEditor chapterId="ch-1" courseId="c-1" defaultTitle="Эссе" />, { wrapper: Wrapper })
    await screen.findByDisplayValue("Эссе")

    await user.click(screen.getByRole("button", { name: "Отмена" }))

    await waitFor(() => expect(screen.getByRole("button", { name: "Новое задание" })).toBeInTheDocument())
  })
})
