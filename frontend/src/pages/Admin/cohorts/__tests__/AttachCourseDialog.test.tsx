/** «Every course is already attached» over a failed read sent the admin away believing there was nothing to attach. */
import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { AttachCourseDialog } from "../AttachCourseDialog"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("AttachCourseDialog", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("does not call a catalogue it could not read «all attached», and asks again on request", async () => {
    const list = vi
      .spyOn(coursesService, "getCourses")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue([{ id: "k1", title: "Деяния", status: "published" } as never])
    render(<AttachCourseDialog open onClose={vi.fn()} cohortId="c1" attachedCourseIds={[]} onAttached={vi.fn()} />, {
      wrapper: Wrapper,
    })

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.queryByText("Все доступные курсы уже привязаны.")).toBeNull()
    expect(screen.getByRole("button", { name: "Привязать" })).toBeDisabled()

    await userEvent.click(screen.getByRole("button", { name: "Повторить" }))

    expect(await screen.findByRole("combobox", { name: "Курс" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Привязать" })).toBeEnabled()
    expect(list).toHaveBeenCalledTimes(2)
  })
})
