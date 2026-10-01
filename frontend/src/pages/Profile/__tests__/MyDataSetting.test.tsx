/** "Download my data" hands the server's file to the browser under its own name. */
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import api from "@/services/api"
import { MyDataSetting } from "../MyDataSetting"

describe("MyDataSetting", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("downloads the export with the filename the server gave it", async () => {
    const user = userEvent.setup()
    const blob = new Blob(["{}"], { type: "application/json" })
    const get = vi.spyOn(api, "get").mockResolvedValue({
      data: blob,
      headers: { "content-disposition": 'attachment; filename="equip-my-data-2026-10-01.json"' },
    })
    const create = vi.fn(() => "blob:mine")
    Object.defineProperty(URL, "createObjectURL", { value: create, configurable: true })
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true })
    const clicked: HTMLAnchorElement[] = []
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this)
    })

    render(
      <I18nextProvider i18n={i18n}>
        <MyDataSetting />
      </I18nextProvider>,
    )
    await user.click(screen.getByRole("button", { name: "Скачать" }))
    await waitFor(() => expect(clicked).toHaveLength(1))
    expect(get).toHaveBeenCalledWith("/users/me/export", { responseType: "blob" })
    expect(create).toHaveBeenCalledWith(blob)
    expect(clicked[0]!.download).toBe("equip-my-data-2026-10-01.json")
    expect(clicked[0]!.href).toBe("blob:mine")
  })
})
