/** "Recording" beside "Join": only for a web address, opened beside the lesson. */
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeAll, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { RecordingLink } from "../RecordingLink"

describe("RecordingLink", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })

  it("links the recording, named for its session", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <RecordingLink url="https://youtu.be/abc" title="Занятие 3" />
      </I18nextProvider>,
    )
    const link = screen.getByRole("link", { name: "Смотреть запись — Занятие 3" })
    expect(link).toHaveAttribute("href", "https://youtu.be/abc")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it.each([null, "", "javascript:alert(1)"])("renders nothing for %j", (url) => {
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <RecordingLink url={url} title="x" />
      </I18nextProvider>,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
