import { act, fireEvent, render, renderHook, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { loadReadingPrefs, useReadingPrefs } from "@/lib/readingPrefs"
import { ReadingControls } from "../ReadingControls"

/** "Aa" beside a reading lesson: a size up or down, and easy reading. */
describe("reading preferences", () => {
  beforeEach(async () => {
    localStorage.clear()
    await i18n.changeLanguage("ru")
  })
  afterEach(() => vi.restoreAllMocks())

  it("start at the defaults, and survive storage that throws", () => {
    expect(loadReadingPrefs()).toEqual({ size: "m", easy: false })
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked")
    })
    expect(loadReadingPrefs()).toEqual({ size: "m", easy: false })
  })

  it("are remembered on the device", () => {
    const { result } = renderHook(() => useReadingPrefs())
    act(() => result.current[1]({ size: "xl" }))
    act(() => result.current[1]({ easy: true }))
    expect(loadReadingPrefs()).toEqual({ size: "xl", easy: true })
  })

  it("ignore a stored value from somewhere else", () => {
    localStorage.setItem("equip:reading", JSON.stringify({ size: "huge", easy: "yes" }))
    expect(loadReadingPrefs()).toEqual({ size: "m", easy: false })
  })

  it("the panel shows the current size and changes it", () => {
    const onChange = vi.fn()
    render(
      <I18nextProvider i18n={i18n}>
        <ReadingControls prefs={{ size: "m", easy: false }} onChange={onChange} />
      </I18nextProvider>,
    )
    fireEvent.click(screen.getByRole("button", { name: i18n.t("chapter.reading.label") }))
    expect(screen.getByRole("button", { name: i18n.t("chapter.reading.sizes.m") })).toHaveAttribute("aria-pressed", "true")
    fireEvent.click(screen.getByRole("button", { name: i18n.t("chapter.reading.sizes.l") }))
    expect(onChange).toHaveBeenCalledWith({ size: "l" })
  })
})
