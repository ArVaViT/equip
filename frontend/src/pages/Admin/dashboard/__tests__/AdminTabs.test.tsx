import { useState } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { AdminTabs } from "../AdminTabs"
import type { AdminTab } from "../constants"

const ALL: readonly AdminTab[] = ["overview", "organizations", "cohorts", "invitations", "translations", "audit", "school"]

/**
 * Seven tabs are wider than a laptop: the row scrolls instead of wrapping,
 * and a tab opened by link is brought into view rather than left past the
 * scrolled edge.
 */
describe("AdminTabs", () => {
  const original = Element.prototype.scrollIntoView
  afterEach(() => {
    Element.prototype.scrollIntoView = original
  })

  it("moves between tabs with the arrow keys, and keeps only the open one in the tab order", async () => {
    // The strip said role="tablist" but behaved as seven buttons: Tab walked
    // through all of them, and the arrows did nothing — unlike the course
    // page's and the profile's tabs.
    function Harness() {
      const [active, setActive] = useState<AdminTab>("overview")
      return <AdminTabs active={active} onChange={setActive} tabs={ALL} />
    }
    const user = userEvent.setup()
    render(
      <I18nextProvider i18n={i18n}>
        <Harness />
      </I18nextProvider>,
    )
    const tabs = screen.getAllByRole("tab")
    expect(tabs.map((tab) => tab.tabIndex)).toEqual([0, -1, -1, -1, -1, -1, -1])

    tabs[0]!.focus()
    await user.keyboard("{ArrowRight}")
    expect(screen.getByRole("tab", { selected: true })).toBe(tabs[1])
    expect(document.activeElement).toBe(tabs[1])

    await user.keyboard("{End}")
    expect(screen.getByRole("tab", { selected: true })).toBe(tabs[6])
    await user.keyboard("{ArrowRight}")
    expect(screen.getByRole("tab", { selected: true })).toBe(tabs[0])
    expect(document.activeElement).toBe(tabs[0])
  })

  it("scrolls the open tab into view, and only that one", () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    render(
      <I18nextProvider i18n={i18n}>
        <AdminTabs active="school" onChange={() => {}} tabs={ALL} />
      </I18nextProvider>,
    )
    expect(scroll).toHaveBeenCalledTimes(1)
    expect(scroll.mock.contexts[0]).toBe(screen.getByRole("tab", { selected: true }))
  })

  it("keeps every label on one line in a row that scrolls", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AdminTabs active="overview" onChange={() => {}} tabs={ALL} />
      </I18nextProvider>,
    )
    expect(screen.getByRole("tablist").className).toContain("overflow-x-auto")
    for (const tab of screen.getAllByRole("tab")) expect(tab.className).toContain("whitespace-nowrap")
  })
})
