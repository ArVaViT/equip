import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { appendComment } from "@/lib/feedback"
import type { User } from "@/types"

const editCommentLibrary = vi.fn()
vi.mock("@/services/users", () => ({
  COMMENT_MAX_LENGTH: 500,
  usersService: { editCommentLibrary: (...a: unknown[]) => editCommentLibrary(...a) },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
const applyUser = vi.fn()
let currentUser: User
import { AuthContext } from "@/context/auth-context"
import { CommentLibrary } from "../CommentLibrary"

/** A teacher's saved remarks, one click into the feedback — added, never replacing. */
describe("CommentLibrary", () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage("ru")
    currentUser = { id: "t1", role: "teacher", comment_library: ["Цитируйте стих, а не только главу."] } as unknown as User
  })

  function open(current: string, onInsert = vi.fn()) {
    render(
      <I18nextProvider i18n={i18n}>
        <AuthContext.Provider value={{ user: currentUser, applyUser } as never}>
          <CommentLibrary current={current} onInsert={onInsert} />
        </AuthContext.Provider>
      </I18nextProvider>,
    )
    fireEvent.click(screen.getByRole("button", { name: i18n.t("grading.library.open", { count: 1 }) }))
    return onInsert
  }

  it("puts a saved remark into the feedback", () => {
    const onInsert = open("Хорошая работа.")
    fireEvent.click(screen.getByRole("button", { name: "Цитируйте стих, а не только главу." }))
    expect(onInsert).toHaveBeenCalledWith("Цитируйте стих, а не только главу.")
    // …after what is already written, on its own line.
    expect(appendComment("Хорошая работа.  ", "Цитируйте стих.")).toBe("Хорошая работа.\nЦитируйте стих.")
    expect(appendComment("", "Цитируйте стих.")).toBe("Цитируйте стих.")
  })

  it("saves what the teacher just wrote, and removes a remark", async () => {
    editCommentLibrary.mockResolvedValue(["Новое замечание", "Цитируйте стих, а не только главу."])
    open("  Новое замечание  ")
    fireEvent.click(screen.getByRole("button", { name: i18n.t("grading.library.save") }))
    await waitFor(() => expect(editCommentLibrary).toHaveBeenCalledWith({ add: "Новое замечание" }))
    expect(applyUser).toHaveBeenCalledWith({ id: "t1", comment_library: ["Новое замечание", "Цитируйте стих, а не только главу."] })
    fireEvent.click(screen.getByRole("button", { name: i18n.t("grading.library.remove", { comment: "Цитируйте стих, а не только главу." }) }))
    await waitFor(() => expect(editCommentLibrary).toHaveBeenCalledWith({ remove: "Цитируйте стих, а не только главу." }))
  })

  it("has nothing to save from an empty box, or a remark already saved", () => {
    open("   ")
    expect(screen.getByRole("button", { name: i18n.t("grading.library.save") })).toBeDisabled()
  })
})
