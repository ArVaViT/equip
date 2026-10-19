import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { GradeTableTab } from "../GradeTableTab"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("GradeTableTab when the matrix could not be read", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("offers to ask again", async () => {
    const onReload = vi.fn()
    render(
      <GradeTableTab
        progressData={null}
        orderedModules={[]}
        moduleChapterMap={new Map()}
        studentChapterMap={new Map()}
        tableStudents={[]}
        summaryByStudent={new Map()}
        forms={new Map()}
        saving={null}
        expandedId={null}
        onUpdateForm={vi.fn()}
        onSaveGrade={vi.fn()}
        onToggleExpand={vi.fn()}
        onReload={onReload}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByRole("alert")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect(onReload).toHaveBeenCalledTimes(1)
  })
})
