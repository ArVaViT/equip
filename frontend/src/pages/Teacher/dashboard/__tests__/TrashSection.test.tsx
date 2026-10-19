/** «Trash is empty» over a failed request told a teacher their deleted course was gone. */
import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/components/ui/alert-dialog", () => ({ useConfirm: () => async () => true }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { TrashSection } from "../TrashSection"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("TrashSection", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
  })

  it("does not call a bin it could not read empty, and asks again on request", async () => {
    const list = vi
      .spyOn(coursesService, "getTrashedCourses")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue([{ id: "k1", title: "Acts", deleted_at: "2026-10-01T00:00:00Z" } as never])
    render(<TrashSection visible onToggle={vi.fn()} onRestore={vi.fn()} />, { wrapper: Wrapper })

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.queryByText("Trash is empty.")).toBeNull()
    await userEvent.click(screen.getByRole("button", { name: "Try again" }))

    expect(await screen.findByText("Acts")).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })
})
