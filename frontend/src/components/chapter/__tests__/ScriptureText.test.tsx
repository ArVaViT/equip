/** An assignment's brief: the cited verse opens, the rest is the text as written. */
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { scriptureService } from "@/services/scripture"
import { ScriptureText } from "../ScriptureText"

function show(text: string) {
  return render(
    <I18nextProvider i18n={i18n}>
      <p>
        <ScriptureText text={text} />
      </p>
    </I18nextProvider>,
  )
}

describe("ScriptureText", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("turns the cited verse into a button that opens it", async () => {
    const user = userEvent.setup()
    vi.spyOn(scriptureService, "passagesIn").mockResolvedValue([
      { written: "Деян. 2:42", ref: "acts 2:42", text: "И они постоянно пребывали в учении Апостолов…", edition: "nrt" },
    ])
    const { container } = show("Прочитайте Деян. 2:42 и ответьте на вопрос.")
    const button = await screen.findByRole("button", { name: "Открыть стих Деян. 2:42" })
    expect(container.textContent).toBe("Прочитайте Деян. 2:42 и ответьте на вопрос.")
    await user.click(button)
    expect(await screen.findByText("И они постоянно пребывали в учении Апостолов…")).toBeInTheDocument()
  })

  it("is the text as written when nothing is cited", async () => {
    vi.spyOn(scriptureService, "passagesIn").mockResolvedValue([])
    const { container } = show("Напишите страницу о Пятидесятнице.")
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe("Напишите страницу о Пятидесятнице.")
    expect(screen.queryByRole("button")).toBeNull()
  })
})
