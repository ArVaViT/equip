import React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Announcement } from "@/types"
import { AnnouncementPager } from "@/components/announcements/AnnouncementPager"

/**
 * The teacher can now fix a post instead of deleting it. The edit
 * affordance follows the same rules as delete: present only when the
 * host passes a handler, and it always reports the announcement the
 * reader is looking at — not the first one, not a stale one.
 */

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const make = (id: string, title: string, content = ""): Announcement => ({
  id,
  title,
  content,
  course_id: "c1",
  created_by: "00000000-0000-0000-0000-000000000000",
  created_at: "2026-05-18T12:00:00Z",
  updated_at: "2026-05-18T12:00:00Z",
})

describe("AnnouncementPager — editing", () => {
  it("shows no edit button on a read-only feed", () => {
    render(<AnnouncementPager announcements={[make("a", "First")]} />, { wrapper: Wrapper })
    expect(screen.queryByRole("button", { name: /edit announcement/i })).not.toBeInTheDocument()
  })

  it("reports the announcement currently on screen, not the first one", async () => {
    const onEdit = vi.fn()
    const user = userEvent.setup()
    const second = make("b", "Second", "Body of the second")
    render(
      <AnnouncementPager announcements={[make("a", "First"), second]} onEdit={onEdit} onDelete={vi.fn()} />,
      { wrapper: Wrapper },
    )
    await user.click(screen.getByRole("button", { name: /next announcement/i }))
    await user.click(screen.getByRole("button", { name: /edit announcement second/i }))
    expect(onEdit).toHaveBeenCalledTimes(1)
    expect(onEdit).toHaveBeenCalledWith(second)
  })

  it("turns an address in the body into a link", () => {
    render(
      <AnnouncementPager
        announcements={[make("a", "Room", "Join: https://zoom.us/j/42?pwd=x&y — see you")]}
      />,
      { wrapper: Wrapper },
    )
    const link = screen.getByRole("link", { name: "https://zoom.us/j/42?pwd=x&y" })
    expect(link).toHaveAttribute("href", "https://zoom.us/j/42?pwd=x&y")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })
})
