/**
 * A lesson holds one quiz. The server refuses a second
 * (``quiz.already_exists``), so a second quiz block could never be filled:
 * it sat empty with nothing to edit (2026-10-03). The menu stops offering
 * it once the lesson has one.
 */

import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { AddBlockMenu } from "../AddBlockMenu"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

async function openMenu(hasQuiz: boolean) {
  const onAdd = vi.fn()
  const user = userEvent.setup()
  render(<AddBlockMenu onAdd={onAdd} adding={false} hasQuiz={hasQuiz} />, { wrapper: Wrapper })
  await user.click(screen.getByRole("button", { name: "Add Block" }))
  return { user, onAdd }
}

describe("the Add Block menu and the lesson's one quiz", () => {
  it("offers a quiz block while the lesson has none", async () => {
    const { user, onAdd } = await openMenu(false)
    await user.click(screen.getByRole("menuitem", { name: "Quiz" }))
    expect(onAdd).toHaveBeenCalledWith("quiz")
  })

  it("stops offering a quiz block once the lesson has one, and keeps the rest", async () => {
    await openMenu(true)
    expect(screen.queryByRole("menuitem", { name: "Quiz" })).not.toBeInTheDocument()
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Text", "Assignment", "File"])
  })
})
