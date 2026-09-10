import { I18nextProvider } from "react-i18next"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { ChapterBlock } from "@/types"
import { FileBlockEditor } from "../FileBlockEditor"

// The teacher who uploaded `Lesson_1__9-12-26.pdf` clicked its name four
// times across 2026-09-07 and -08 and nothing happened: the name was a
// `<span>`. Signing on click is what the student's chapter page already
// does — a stored signature would outlive a JWT rotation.
const getSignedBlockFileUrl = vi.fn()
vi.mock("@/services/storage", () => ({
  storageService: {
    getSignedBlockFileUrl: (...args: [string, string]) => getSignedBlockFileUrl(...args),
    uploadBlockFile: vi.fn(),
  },
}))

vi.mock("@/services/courses", () => ({
  coursesService: { updateBlock: vi.fn() },
}))

const toastMock = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (...args: unknown[]) => toastMock(...args) }))

const BLOCK: ChapterBlock = {
  id: "b-1",
  chapter_id: "ch-1",
  block_type: "file",
  order_index: 0,
  file_bucket: "course-materials",
  file_path: "course-1/ch-1/1788831466882-Lesson_1__9-12-26.pdf",
  file_name: "Lesson_1__9-12-26.pdf",
} as ChapterBlock

function renderEditor(block: ChapterBlock = BLOCK) {
  return render(
    <I18nextProvider i18n={i18n}>
      <FileBlockEditor block={block} courseId="course-1" chapterId="ch-1" onUpdated={vi.fn()} />
    </I18nextProvider>,
  )
}

describe("FileBlockEditor — the attached file opens", () => {
  beforeEach(() => {
    getSignedBlockFileUrl.mockReset()
    getSignedBlockFileUrl.mockResolvedValue("https://signed.example/one-hour")
    toastMock.mockReset()
    vi.stubGlobal("open", vi.fn())
  })

  it("signs and opens the file when its name is clicked", async () => {
    renderEditor()
    await userEvent.click(screen.getByRole("button", { name: /Lesson_1__9-12-26\.pdf/ }))

    await waitFor(() =>
      expect(getSignedBlockFileUrl).toHaveBeenCalledWith(
        "course-materials",
        "course-1/ch-1/1788831466882-Lesson_1__9-12-26.pdf",
      ),
    )
    expect(window.open).toHaveBeenCalledWith(
      "https://signed.example/one-hour",
      "_blank",
      "noopener,noreferrer",
    )
  })

  it("says so when signing fails instead of doing nothing", async () => {
    getSignedBlockFileUrl.mockRejectedValue(new Error("nope"))
    renderEditor()
    await userEvent.click(screen.getByRole("button", { name: /Lesson_1__9-12-26\.pdf/ }))

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    expect(window.open).not.toHaveBeenCalled()
  })

  it("does not offer to open a block with no file yet", () => {
    renderEditor({ ...BLOCK, file_bucket: null, file_path: null, file_name: null } as ChapterBlock)
    expect(screen.queryByRole("button", { name: /Lesson_1/ })).not.toBeInTheDocument()
  })
})
