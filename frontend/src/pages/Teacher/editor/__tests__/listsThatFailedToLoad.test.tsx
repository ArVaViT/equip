/**
 * A list that could not be read is not an empty list.
 *
 * «No announcements yet» over a failed request had the teacher posting the
 * notice again — and every student mailed twice; «No events yet» invited a
 * second weekly series.
 */
import type { ReactNode } from "react"
import { render, renderHook, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { AnnouncementsModal } from "../AnnouncementsModal"
import { useAnnouncementsSection } from "../useAnnouncementsSection"
import { useEventsSection } from "../useEventsSection"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("lists the course editor could not read", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
  })

  it("announcements: says the read failed, and asks again on request", async () => {
    const list = vi
      .spyOn(coursesService, "getAnnouncementsForEdit")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue([])
    const { result } = renderHook(() => useAnnouncementsSection("c1", vi.fn(async () => true)))
    await waitFor(() => expect(result.current.loadFailed).toBe(true))
    result.current.reload()
    await waitFor(() => expect(result.current.loadFailed).toBe(false))
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("events: the same", async () => {
    const list = vi
      .spyOn(coursesService, "getCourseEventsForEdit")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue([])
    const { result } = renderHook(() => useEventsSection("c1", vi.fn(async () => true)))
    await waitFor(() => expect(result.current.loadFailed).toBe(true))
    result.current.reloadList()
    await waitFor(() => expect(result.current.loadFailed).toBe(false))
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("the announcements dialog shows the failure with a retry, not «no announcements yet»", async () => {
    const onReload = vi.fn()
    render(
      <AnnouncementsModal
        open
        onClose={vi.fn()}
        announcements={[]}
        title=""
        content=""
        onTitleChange={vi.fn()}
        onContentChange={vi.fn()}
        editingId={null}
        posting={false}
        onPost={vi.fn()}
        onEdit={vi.fn()}
        onCancelEdit={vi.fn()}
        onDelete={vi.fn()}
        loadFailed
        onReload={onReload}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.queryByText(i18n.t("teacherEditor.modals.announcements.empty"))).toBeNull()
    expect(screen.getByRole("alert")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: i18n.t("common.tryAgain") }))
    expect(onReload).toHaveBeenCalledTimes(1)
  })
})
