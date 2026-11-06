import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { MaterialsModal } from "../MaterialsModal"

const files = [
  { name: "Syllabus.pdf", path: "c/syllabus.pdf" },
  { name: "Reading list.docx", path: "c/reading.docx" },
]

const show = (onDownload = vi.fn(), downloadingPath: string | null = null) => {
  render(
    <I18nextProvider i18n={i18n}>
      <MaterialsModal open onClose={() => {}} materials={files as never} downloadingPath={downloadingPath} onDownload={onDownload} />
    </I18nextProvider>,
  )
  return onDownload
}

/**
 * The whole row downloads. RUM, 2026-10-24 → 11-03: every new student of one
 * course tapped a file's name four times and nothing happened — only the small
 * icon on the right answered.
 */
describe("MaterialsModal", () => {
  it("downloads a file when its name is tapped", async () => {
    const onDownload = show()
    await userEvent.click(screen.getByText("Reading list.docx"))
    expect(onDownload).toHaveBeenCalledWith("c/reading.docx")
  })

  it("is one button per file, named for what it does", () => {
    show()
    expect(screen.getAllByRole("button", { name: /Syllabus\.pdf|Reading list\.docx/ })).toHaveLength(2)
  })

  it("does not start a second download of the file already coming", async () => {
    const onDownload = show(vi.fn(), "c/syllabus.pdf")
    await userEvent.click(screen.getByText("Syllabus.pdf"))
    expect(onDownload).not.toHaveBeenCalled()
  })
})
