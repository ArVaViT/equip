/**
 * The card a tapped reference opens: the verse, its edition, closed with
 * Escape.
 */
import React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { VerseCard } from "../VerseCard"

describe("VerseCard", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })

  it("shows the verse and its edition, and closes on Escape", async () => {
    const user = userEvent.setup()
    const anchor = document.createElement("button")
    anchor.textContent = "Деян. 1:8"
    document.body.append(anchor)
    const onClose = vi.fn()
    render(
      <I18nextProvider i18n={i18n}>
        <VerseCard
          anchor={anchor}
          passage={{ written: "Деян. 1:8", ref: "acts 1:8", text: "но вы примете силу…", edition: "nrt" }}
          onClose={onClose}
        />
      </I18nextProvider>,
    )
    expect(screen.getByText("но вы примете силу…")).toBeInTheDocument()
    expect(screen.getByText("Новый русский перевод")).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(onClose).toHaveBeenCalled()
    anchor.remove()
  })

  it("gives focus back to the reference on Escape, but not when the reader clicked elsewhere", async () => {
    const user = userEvent.setup()
    const anchor = document.createElement("button")
    anchor.textContent = "Ин 3:16"
    const elsewhere = document.createElement("input")
    document.body.append(anchor, elsewhere)
    const passage = { written: "Ин 3:16", ref: "john 3:16", text: "Ибо так возлюбил Бог мир…", edition: "nrt" }

    function Harness() {
      const [open, setOpen] = React.useState(true)
      return (
        <I18nextProvider i18n={i18n}>
          {open && <VerseCard anchor={anchor} passage={passage} onClose={() => setOpen(false)} />}
        </I18nextProvider>
      )
    }

    const first = render(<Harness />)
    await user.keyboard("{Escape}")
    expect(document.activeElement).toBe(anchor)
    first.unmount()

    render(<Harness />)
    await user.click(elsewhere)
    expect(screen.queryByText(passage.text)).toBeNull()
    expect(document.activeElement).toBe(elsewhere)
    anchor.remove()
    elsewhere.remove()
  })
})
