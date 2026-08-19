import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { AuthContext } from "@/context/auth-context"
import { coursesService } from "@/services/courses"
import { rubricsService } from "@/services/rubrics"
import AssignmentPanel from "../AssignmentPanel"
import type { Assignment, AssignmentSubmission } from "@/types"

/**
 * "We could not find out" is not "you have not handed it in".
 *
 * The panel used to answer a failed submissions fetch with `[]`, which renders
 * identically to a student who has submitted nothing: an empty textarea and a
 * Submit button, over work that may already be sitting on the server. On a
 * flaky connection — which is most of them, for most of these students — the
 * likely next move is to type the essay again.
 */
const ASSIGNMENT: Assignment = {
  id: "a-1",
  chapter_id: "ch-1",
  title: "Эссе по Деяниям 2",
  description: null,
  max_score: 100,
  due_date: null,
} as Assignment

const SUBMITTED: AssignmentSubmission = {
  id: "sub-1",
  assignment_id: "a-1",
  student_id: "student-1",
  content: "Уже сдано",
  file_url: null,
  submitted_at: "2026-08-12T09:00:00Z",
  status: "submitted",
  grade: null,
  feedback: null,
} as AssignmentSubmission

const STUDENT = { id: "student-1", email: "s@example.org" } as never

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      {/* The panel keeps a per-user draft key, so it needs a user. */}
      <AuthContext.Provider
        value={{
          user: STUDENT,
          loading: false,
          login: vi.fn(),
          register: vi.fn(),
          signInWithGoogle: vi.fn(),
          resetPassword: vi.fn(),
          logout: vi.fn(),
          refreshUser: vi.fn().mockResolvedValue(undefined),
          applyUser: vi.fn(),
        }}
      >
        {children}
      </AuthContext.Provider>
    </I18nextProvider>
  )
}

function show() {
  return render(<AssignmentPanel chapterId="ch-1" assignmentId="a-1" />, { wrapper: Wrapper })
}

describe("AssignmentPanel — a failed lookup is not an empty one", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
    vi.spyOn(coursesService, "getChapterAssignments").mockResolvedValue([ASSIGNMENT])
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({
      rubric: null,
      marks: [],
      earned: null,
      out_of: null,
    })
  })

  it("hides the submit form when the submissions fetch failed", async () => {
    vi.spyOn(coursesService, "getMySubmissions").mockRejectedValue(new Error("network"))
    show()

    expect(await screen.findByText(/Не удалось проверить/)).toBeInTheDocument()
    // The whole point: no way to submit a second copy of something that may
    // already exist.
    expect(screen.queryByRole("button", { name: /Отправить/i })).not.toBeInTheDocument()
  })

  it("says why the form is missing, rather than just that something broke", async () => {
    vi.spyOn(coursesService, "getMySubmissions").mockRejectedValue(new Error("network"))
    show()

    // «Ошибка» alone leaves the student to guess whether their work is safe.
    expect(await screen.findByText(/вторая копия только запутает/)).toBeInTheDocument()
  })

  it("recovers the real answer on retry", async () => {
    const fetch = vi
      .spyOn(coursesService, "getMySubmissions")
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue([SUBMITTED])
    show()

    await userEvent.click(await screen.findByRole("button", { name: /Проверить снова/ }))

    await waitFor(() => expect(screen.queryByText(/Не удалось проверить/)).not.toBeInTheDocument())
    expect(await screen.findByText(/Отправлено|На проверке/)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it("still shows the form when the student genuinely has not submitted", async () => {
    vi.spyOn(coursesService, "getMySubmissions").mockResolvedValue([])
    show()

    expect(await screen.findByRole("button", { name: /Отправить/i })).toBeInTheDocument()
    expect(screen.queryByText(/Не удалось проверить/)).not.toBeInTheDocument()
  })
})
