/**
 * A notification with nothing in your language is a row with a time on it.
 *
 * The backend stopped substituting another language when a translation is
 * missing — deliberately — and returns an empty string instead. Every
 * surface that renders that string without a guard now shows the reader a
 * blank where the sentence should be, which reads as a broken app rather
 * than as missing content. The bell is the worst of them: the row is still
 * clickable, still timestamped, and says nothing at all.
 */

import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { I18nextProvider } from "react-i18next"

import i18n from "@/i18n/config"
import { NotificationItem } from "../NotificationItem"
import type { Notification } from "@/types"

const notification = (over: Partial<Notification>): Notification =>
  ({
    id: "n-1",
    user_id: "u-1",
    type: "announcement",
    title: "Ephesians is open",
    message: "The next module unlocks today.",
    link: null,
    is_read: false,
    created_at: new Date().toISOString(),
    metadata: null,
    ...over,
  }) as Notification

function renderItem(n: Notification) {
  return render(
    <I18nextProvider i18n={i18n}>
      <NotificationItem notification={n} onActivate={() => {}} onDelete={() => {}} />
    </I18nextProvider>,
  )
}

describe("a notification nobody translated", () => {
  it("says so instead of rendering an empty row", () => {
    renderItem(notification({ title: "", message: "" }))
    expect(screen.getAllByText(/not in your language yet/i).length).toBeGreaterThan(0)
  })

  it("leaves a translated notification alone", () => {
    renderItem(notification({}))
    expect(screen.getByText("Ephesians is open")).toBeInTheDocument()
    expect(screen.queryByText(/not in your language yet/i)).not.toBeInTheDocument()
  })
})
