/** A press that does nothing, silently, reads as a broken button. */
import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (o: unknown) => toast(o) }))

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { useNotifications } from "../useNotifications"

describe("useNotifications — actions that fail", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
    toast.mockClear()
    vi.spyOn(coursesService, "getUnreadCount").mockResolvedValue(1)
    vi.spyOn(coursesService, "getNotifications").mockResolvedValue({
      items: [{ id: "n1", is_read: false, type: "x", title: "t", created_at: "2026-10-01T00:00:00Z" }],
      total: 1,
      has_more: false,
    } as never)
  })

  it("says so when «mark all read» is refused, and marks nothing on screen", async () => {
    vi.spyOn(coursesService, "markAllAsRead").mockRejectedValue(new Error("offline"))
    const { result } = renderHook(() => useNotifications(true))
    await waitFor(() => expect(result.current.notifications.length).toBe(1))
    await act(async () => {
      await result.current.markAllRead()
    })
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: "destructive" }))
    expect(result.current.notifications[0]?.is_read).toBe(false)
  })

  it("says so when a delete is refused, and keeps the notification", async () => {
    vi.spyOn(coursesService, "deleteNotification").mockRejectedValue(new Error("offline"))
    const { result } = renderHook(() => useNotifications(true))
    await waitFor(() => expect(result.current.notifications.length).toBe(1))
    await act(async () => {
      await result.current.remove("n1")
    })
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: "destructive" }))
    expect(result.current.notifications.length).toBe(1)
  })
})
