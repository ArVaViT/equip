/** The bell's "a recording is ready" carries the way to watch it. */
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Notification } from "@/types"
import { NotificationItem } from "../notifications/NotificationItem"

describe("a recording notification", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })

  it("has a Recording button beside the row", () => {
    const notification = {
      id: "n1",
      user_id: "u1",
      type: "recording_ready",
      title: "Запись занятия готова",
      message: "Живое занятие: Деяния 2 — в «Деяния». Её можно посмотреть.",
      link: "/calendar?course=c1",
      is_read: false,
      created_at: new Date().toISOString(),
      metadata: { recording_url: "https://youtu.be/abc" },
    } as unknown as Notification
    render(
      <I18nextProvider i18n={i18n}>
        <NotificationItem notification={notification} onActivate={vi.fn()} onDelete={vi.fn()} />
      </I18nextProvider>,
    )
    expect(screen.getByRole("link", { name: "Смотреть запись — Запись занятия готова" })).toHaveAttribute(
      "href",
      "https://youtu.be/abc",
    )
  })
})
