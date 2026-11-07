import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { AuthContext } from "@/context/auth-context"
import { coursesService } from "@/services/courses"
import { rubricsService } from "@/services/rubrics"
import { storageService } from "@/services/storage"
import { MB } from "@/lib/uploadLimits"
import AssignmentPanel from "../AssignmentPanel"
import type { Assignment, AssignmentSubmission } from "@/types"

/**
 * A sermon outline is a photo of a notebook page or a voice memo. The form
 * took text, or a link to a file put somewhere else first — and in the
 * whole life of the platform nothing was handed in. Now: choose the file,
 * it uploads at once, press send.
 */
const ASSIGNMENT: Assignment = {
  id: "a-1",
  chapter_id: "ch-1",
  title: "Тематическая проповедь",
  description: null,
  max_score: 100,
  due_date: null,
} as Assignment

const STUDENT = { id: "student-1", email: "s@example.org" } as never

const UPLOADED = { bucket: "submissions", path: "c-1/a-1/student-1/1762480000000-propoved.jpg", name: "проповедь.jpg" }

const HANDED_IN: AssignmentSubmission = {
  id: "sub-1",
  assignment_id: "a-1",
  student_id: "student-1",
  content: null,
  file_url: null,
  file_bucket: UPLOADED.bucket,
  file_path: UPLOADED.path,
  file_name: UPLOADED.name,
  submitted_at: "2026-11-07T09:00:00Z",
  status: "submitted",
  grade: null,
  feedback: null,
  graded_by: null,
  graded_at: null,
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <AuthContext.Provider
        value={{
          user: STUDENT,
          loading: false,
          login: vi.fn(),
          register: vi.fn(),
          signInWithGoogle: vi.fn(),
          sendSignInLink: vi.fn(),
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

function show(aiPolicy: "ai_open" | "ai_with_disclosure" | "ai_forbidden" = "ai_with_disclosure") {
  return render(<AssignmentPanel courseId="c-1" chapterId="ch-1" assignmentId="a-1" aiPolicy={aiPolicy} />, {
    wrapper: Wrapper,
  })
}

function photo(name = "проповедь.jpg", bytes = 2 * MB, type = "image/jpeg"): File {
  const file = new File(["x"], name, { type })
  Object.defineProperty(file, "size", { value: bytes })
  return file
}

async function attach(file: File) {
  const input = screen.getByLabelText("Прикрепить файл", { selector: "input" })
  await userEvent.upload(input, file, { applyAccept: false })
}

describe("AssignmentPanel — handing in a file from the phone", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
    vi.spyOn(coursesService, "getChapterAssignments").mockResolvedValue([ASSIGNMENT])
    vi.spyOn(coursesService, "getMySubmissions").mockResolvedValue([])
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({ rubric: null, marks: [], earned: null, out_of: null })
    vi.spyOn(storageService, "removeSubmissionFile").mockResolvedValue(undefined)
  })

  it("uploads the moment a file is chosen and shows it as a chip with its size", async () => {
    const upload = vi.spyOn(storageService, "uploadSubmissionFile").mockResolvedValue(UPLOADED)
    show()
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await attach(photo())

    expect(upload).toHaveBeenCalledWith("c-1", "a-1", "student-1", expect.any(File), expect.any(Function))
    expect(await screen.findByText("проповедь.jpg")).toBeInTheDocument()
    expect(screen.getByText(/^2(,0)? МБ$/)).toBeInTheDocument()
    // The big button gives way to the chip: one file, one place.
    expect(screen.queryByRole("button", { name: "Прикрепить файл" })).not.toBeInTheDocument()
  })

  it("shows how far the upload got, and waits for it before sending", async () => {
    let report: ((fraction: number) => void) | undefined
    let finish: (() => void) | undefined
    vi.spyOn(storageService, "uploadSubmissionFile").mockImplementation(
      (_c, _a, _s, _f, onProgress) =>
        new Promise((resolve) => {
          report = onProgress
          finish = () => resolve(UPLOADED)
        }),
    )
    show("ai_open")
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await attach(photo())
    await waitFor(() => expect(report).toBeDefined())
    report!(0.4)

    expect(await screen.findByRole("progressbar")).toHaveAttribute("aria-valuenow", "40")
    // Something to hand in exists, but the bytes are still travelling.
    expect(screen.getByRole("button", { name: /Отправить/ })).toBeDisabled()

    finish!()
    await waitFor(() => expect(screen.getByRole("button", { name: /Отправить/ })).toBeEnabled())
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
  })

  it("hands in the file alone, with the key and the name, and no text", async () => {
    vi.spyOn(storageService, "uploadSubmissionFile").mockResolvedValue(UPLOADED)
    const submit = vi.spyOn(coursesService, "submitAssignment").mockResolvedValue(HANDED_IN)
    show("ai_open")
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await attach(photo())
    await screen.findByText("проповедь.jpg")
    await userEvent.click(screen.getByRole("button", { name: /Отправить/ }))

    expect(submit).toHaveBeenCalledWith("a-1", {
      content: undefined,
      file_url: undefined,
      file: { path: UPLOADED.path, name: UPLOADED.name },
      declaration: undefined,
    })
    // Handed in: the status, and the file as a chip that opens.
    expect(await screen.findByText(/Сдано/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Открыть файл проповедь.jpg" })).toBeInTheDocument()
  })

  it("opens the handed-in file through a URL signed on click", async () => {
    vi.spyOn(coursesService, "getMySubmissions").mockResolvedValue([HANDED_IN])
    const sign = vi.spyOn(storageService, "getSignedSubmissionFileUrl").mockResolvedValue("https://signed.example/x")
    const open = vi.spyOn(window, "open").mockImplementation(() => null)
    show()

    await userEvent.click(await screen.findByRole("button", { name: "Открыть файл проповедь.jpg" }))

    await waitFor(() => expect(open).toHaveBeenCalledWith("https://signed.example/x", "_blank", "noopener,noreferrer"))
    expect(sign).toHaveBeenCalledWith(UPLOADED.bucket, UPLOADED.path)
  })

  it("removes a chosen file again, from the screen and from the bucket", async () => {
    vi.spyOn(storageService, "uploadSubmissionFile").mockResolvedValue(UPLOADED)
    const remove = vi.spyOn(storageService, "removeSubmissionFile").mockResolvedValue(undefined)
    show("ai_open")
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await attach(photo())
    await screen.findByText("проповедь.jpg")
    await userEvent.click(screen.getByRole("button", { name: "Убрать файл" }))

    expect(remove).toHaveBeenCalledWith(UPLOADED.path)
    expect(screen.queryByText("проповедь.jpg")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Прикрепить файл" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Отправить/ })).toBeDisabled()
  })

  it("says one sentence about a file over 50 MB and brings out the link field", async () => {
    const upload = vi.spyOn(storageService, "uploadSubmissionFile")
    show("ai_open")
    await screen.findByRole("button", { name: "Прикрепить файл" })
    // Hidden until asked for: a student with a photo does not need a URL.
    expect(screen.queryByRole("textbox", { name: /Ссылка на файл/ })).not.toBeInTheDocument()

    await attach(photo("sermon.mp4", 60 * MB, "video/mp4"))

    expect(await screen.findByText(/Файл больше 50 МБ/)).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: /Ссылка на файл/ })).toBeInTheDocument()
    expect(upload).not.toHaveBeenCalled()
  })

  it("refuses a kind of file the bucket does not take, the same way", async () => {
    const upload = vi.spyOn(storageService, "uploadSubmissionFile")
    show("ai_open")
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await attach(photo("virus.exe", 1 * MB, "application/x-msdownload"))

    expect(await screen.findByText(/Такой файл не подойдёт/)).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: /Ссылка на файл/ })).toBeInTheDocument()
    expect(upload).not.toHaveBeenCalled()
  })

  it("keeps the failed file on screen with the reason, so the student can try again", async () => {
    vi.spyOn(storageService, "uploadSubmissionFile").mockRejectedValue(new TypeError("Failed to fetch"))
    show("ai_open")
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await attach(photo())

    expect(await screen.findByRole("alert")).toHaveTextContent(/Не удалось связаться с хранилищем/)
    expect(screen.getByText("проповедь.jpg")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Отправить/ })).toBeDisabled()
  })

  it("brings out the link field on «или вставить ссылку» and sends the link", async () => {
    const submit = vi.spyOn(coursesService, "submitAssignment").mockResolvedValue({ ...HANDED_IN, file_path: null, file_bucket: null, file_name: null, file_url: "https://youtu.be/x" })
    show("ai_open")
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await userEvent.click(screen.getByRole("button", { name: "или вставить ссылку" }))
    await userEvent.type(screen.getByRole("textbox", { name: /Ссылка на файл/ }), "https://youtu.be/x")
    await userEvent.click(screen.getByRole("button", { name: /Отправить/ }))

    expect(submit).toHaveBeenCalledWith("a-1", expect.objectContaining({ file_url: "https://youtu.be/x", file: undefined }))
  })

  it("waits for the answer about AI where the course has a rule, and sends what was on the screen", async () => {
    vi.spyOn(storageService, "uploadSubmissionFile").mockResolvedValue(UPLOADED)
    const submit = vi.spyOn(coursesService, "submitAssignment").mockResolvedValue(HANDED_IN)
    show("ai_with_disclosure")
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await attach(photo())
    await screen.findByText("проповедь.jpg")
    // The work is there; the answer is not.
    expect(screen.getByRole("button", { name: /Отправить/ })).toBeDisabled()

    await userEvent.click(screen.getByRole("radio", { name: "С ИИ" }))
    await userEvent.type(screen.getByRole("textbox", { name: "Для чего?" }), "перефразировать введение")
    expect(screen.getByText(/Отправляя, вы подтверждаете/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /Отправить/ }))

    expect(submit).toHaveBeenCalledWith(
      "a-1",
      expect.objectContaining({
        file: { path: UPLOADED.path, name: UPLOADED.name },
        declaration: {
          ai_use: "assisted",
          statement: [
            i18n.t("declaration.ai_with_disclosure.rule"),
            i18n.t("declaration.withAi"),
            i18n.t("declaration.bySubmitting"),
          ].join("\n"),
          note: "перефразировать введение",
        },
      }),
    )
  })

  it("does not send the typed text when nothing but the answer about AI is there", async () => {
    const submit = vi.spyOn(coursesService, "submitAssignment")
    show("ai_forbidden")
    await screen.findByRole("button", { name: "Прикрепить файл" })

    await userEvent.click(screen.getByRole("radio", { name: "Без ИИ" }))

    // A declaration alone is not the work (2026-10-03).
    expect(screen.getByRole("button", { name: /Отправить/ })).toBeDisabled()
    expect(submit).not.toHaveBeenCalled()
  })
})
