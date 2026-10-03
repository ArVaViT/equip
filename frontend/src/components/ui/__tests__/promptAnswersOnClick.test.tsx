import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { ConfirmProvider, usePrompt } from "../alert-dialog"

/** OK answers with what was typed — by click, not only by Enter. */
function Asker({ onAnswer }: { onAnswer: (v: string | null) => void }) {
  const prompt = usePrompt()
  return (
    <button type="button" onClick={async () => onAnswer(await prompt({ title: "Link", confirmLabel: "Save" }))}>
      ask
    </button>
  )
}

function renderAsker() {
  const answers: (string | null)[] = []
  render(
    <I18nextProvider i18n={i18n}>
      <ConfirmProvider>
        <Asker onAnswer={(v) => answers.push(v)} />
      </ConfirmProvider>
    </I18nextProvider>,
  )
  return answers
}

describe("usePrompt", () => {
  it("answers with the text when OK is clicked", async () => {
    const answers = renderAsker()
    await userEvent.click(screen.getByText("ask"))
    await userEvent.type(await screen.findByRole("textbox"), "https://youtu.be/x")
    await userEvent.click(screen.getByRole("button", { name: "Save" }))
    await waitFor(() => expect(answers).toEqual(["https://youtu.be/x"]))
  })

  it("answers with the text on Enter, and null on cancel", async () => {
    const answers = renderAsker()
    await userEvent.click(screen.getByText("ask"))
    await userEvent.type(await screen.findByRole("textbox"), "abc{Enter}")
    await waitFor(() => expect(answers).toEqual(["abc"]))
    await userEvent.click(screen.getByText("ask"))
    const box = await screen.findByRole("textbox")
    await act(async () => {
      fireEvent.keyDown(box, { key: "Escape" })
    })
    await waitFor(() => expect(answers).toEqual(["abc", null]))
  })
})
