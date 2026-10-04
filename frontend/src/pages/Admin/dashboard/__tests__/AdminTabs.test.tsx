import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { AdminTabs } from "../AdminTabs"
import type { AdminTab } from "../constants"

const ALL: readonly AdminTab[] = ["overview", "organizations", "cohorts", "invitations", "translations", "audit", "school", "dmca"]

/**
 * Eight tabs are wider than a laptop: the row scrolls instead of wrapping,
 * and a tab opened by link is brought into view rather than left past the
 * scrolled edge.
 */
describe("AdminTabs", () => {
  const original = Element.prototype.scrollIntoView
  afterEach(() => {
    Element.prototype.scrollIntoView = original
  })

  it("scrolls the open tab into view, and only that one", () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    render(
      <I18nextProvider i18n={i18n}>
        <AdminTabs active="dmca" onChange={() => {}} tabs={ALL} />
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
