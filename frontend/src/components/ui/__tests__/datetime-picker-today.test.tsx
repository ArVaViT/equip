import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import { DateTimePicker } from "../datetime-picker"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

/**
 * An empty picker given an hour first takes today's date — the reader's
 * today, the day the grid rings, not the browser's.
 */
describe("DateTimePicker with no date yet", () => {
  afterEach(() => {
    vi.useRealTimers()
    setDisplayTimeZone(null)
  })

  it("puts a typed hour on the reader's today", async () => {
    // 20:00 UTC on 30 September: 1 October in Tokyo, the 30th in Indiana or UTC.
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-09-30T20:00:00Z"))
    setDisplayTimeZone("Asia/Tokyo")
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<DateTimePicker value="" onChange={onChange} />, { wrapper: Wrapper })
    await user.click(screen.getByRole("button"))
    fireEvent.change(await screen.findByLabelText(i18n.t("dateTimePicker.hourAria")), { target: { value: "14" } })
    expect(onChange).toHaveBeenCalledWith("2026-10-01T14:00")
  })
})
